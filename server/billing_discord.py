"""Stripe Checkout and private Discord role reconciliation. One bot process per persistent database."""
import asyncio
import hashlib
import logging
import os
import sqlite3
import time
from pathlib import Path

import aiohttp
import discord

LOG = logging.getLogger(__name__)
ANNOUNCEMENT = ("**Devenir adhérent Cap Investissement · 39 € par mois**\n"
                "L’abonnement ouvre les analyses et les salons adhérents et comprend un entretien individuel de 30 minutes par mois. "
                "Après avoir accepté le règlement, utilise le bouton ci-dessous. Ton lien Stripe te sera envoyé en privé dans Discord. "
                "Les salons s’ouvrent après confirmation du paiement. Tu peux résilier depuis le même bouton : "
                "tu conserves la période payée, puis tu retrouves ton espace gratuit.")

def paid_end(invoice, price):
    if not isinstance(invoice, dict) or invoice.get("status") != "paid" or invoice.get("amount_paid", 0) <= 0:
        return 0
    return max((line["period"]["end"] for line in invoice["lines"]["data"]
                if (line.get("price") or {}).get("id") == price and line.get("type") == "subscription"
                and line.get("amount", 0) > 0 and not line.get("proration")), default=0)

def role_change(until, now, owns_role, managed):
    if until > now and not owns_role:
        return "grant"
    if until <= now and managed:
        return "revoke"
    return "keep"

class Billing(discord.ui.View):
    def __init__(self, client, guild_id):
        super().__init__(timeout=None)
        self.client = client
        self.guild_id = guild_id
        self.price = os.environ["STRIPE_PRICE_ID"]
        self.key = os.environ["STRIPE_SECRET_KEY"]
        self.live = self.key.startswith(("sk_live_", "rk_live_"))
        self.role_name = "Abonné" if self.live else "Abonné test"
        self.lock = asyncio.Lock()
        self.channel = int(os.environ["BILLING_CHANNEL_ID"])
        self.task = None
        path = Path(os.environ["BILLING_DB_PATH"])
        if not path.is_absolute():
            raise ValueError("Indiquer un chemin absolu sur volume persistant")
        self.db = sqlite3.connect(path)
        self.db.execute("CREATE TABLE IF NOT EXISTS members (space TEXT, uid TEXT, customer TEXT, session TEXT, paid_until INTEGER DEFAULT 0, managed INTEGER DEFAULT 0, PRIMARY KEY(space,uid))")
        self.space = f"{guild_id}:{self.price}:{int(self.live)}"

    async def stripe(self, method, route, data=None, idem=None):
        headers = {"Authorization":"Bearer " + self.key, "Stripe-Version":"2024-06-20"}
        if idem:
            headers["Idempotency-Key"] = hashlib.sha256(idem.encode()).hexdigest()
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as session:
            async with session.request(method, "https://api.stripe.com/v1/" + route, headers=headers,
                                       params=data if method == "GET" else None, data=data if method == "POST" else None,
                                       allow_redirects=False) as response:
                if response.status != 200:
                    raise RuntimeError(f"Stripe HTTP {response.status}")
                return await response.json()

    def save(self, query, *args):
        with self.db:
            self.db.execute(query,args)

    async def start(self, guild):
        if self.task and not self.task.done():
            return
        price = await self.stripe("GET","prices/" + self.price)
        if not (price["active"] and price["livemode"] == self.live and price["currency"] == "eur"
                and price["unit_amount"] == 3900 and price["recurring"]["interval"] == "month"
                and price["recurring"]["interval_count"] == 1):
            raise RuntimeError("Prix incompatible")
        roles = [r for r in guild.roles if r.name == self.role_name and not r.managed and r.permissions.value == 0]
        if len(roles) != 1 or roles[0] >= guild.me.top_role:
            raise RuntimeError("Rôle incompatible")
        self.role = roles[0]
        channel = guild.get_channel(self.channel)
        if not isinstance(channel,discord.TextChannel):
            raise RuntimeError("Salon de facturation introuvable")
        if not self.live and channel.permissions_for(guild.default_role).view_channel:
            raise RuntimeError("Le test exige un salon privé")
        if not self.live and any(channel.permissions_for(role).view_channel for role in guild.roles
                                 if not role.managed and not role.permissions.administrator):
            raise RuntimeError("Le test exige un salon réservé aux testeurs invités individuellement")
        config = await self.stripe("GET","billing_portal/configurations/" + os.environ["STRIPE_PORTAL_CONFIG_ID"])
        cancel = config["features"]["subscription_cancel"]
        if not config["active"] or not cancel["enabled"] or cancel["mode"] != "at_period_end":
            raise RuntimeError("Configurer la résiliation en fin de période")
        content = ANNOUNCEMENT if self.live else "**Simulation Stripe · accès de test**\n" + ANNOUNCEMENT
        async for msg in channel.history(limit=None):
            if msg.author.id == self.client.user.id and msg.content == content:
                await msg.edit(view=self)
                break
        else:
            await channel.send(content,view=self,allowed_mentions=discord.AllowedMentions.none())
        self.task = asyncio.create_task(self.reconcile(guild))

    @discord.ui.button(label="S’abonner ou gérer mon abonnement",style=discord.ButtonStyle.primary,custom_id="cap:stripe:v1")
    async def checkout(self, interaction, button):
        await interaction.response.defer(ephemeral=True,thinking=True)
        if (interaction.guild_id != self.guild_id or interaction.channel_id != self.channel
                or not any(r.name == "Membre confirmé" for r in interaction.user.roles)):
            await interaction.followup.send("Accepte d’abord le règlement dans Commencer ici.",ephemeral=True)
            return
        uid = str(interaction.user.id)
        try:
            async with self.lock:
                url = await self.checkout_url(uid)
        except Exception as exc:
            LOG.warning("Checkout indisponible (%s)",type(exc).__name__)
            await interaction.followup.send("Stripe est temporairement indisponible. Réessaie ici.",ephemeral=True)
            return
        await interaction.followup.send(f"[Ouvrir mon espace Stripe]({url})",ephemeral=True)

    async def checkout_url(self, uid):
        row = self.db.execute("SELECT customer,session FROM members WHERE space=? AND uid=?",(self.space,uid)).fetchone()
        if row is None:
            obj = await self.stripe("POST","customers",{"metadata[discord_member]":uid,"metadata[discord_guild]":str(self.guild_id)},self.space+uid+"customer")
            row = (obj["id"],None)
            self.save("INSERT INTO members(space,uid,customer) VALUES(?,?,?)",self.space,uid,row[0])
        customer,previous = row
        target = f"https://discord.com/channels/{self.guild_id}/{self.channel}"
        if previous:
            session = await self.stripe("GET","checkout/sessions/" + previous)
            if session["status"] == "open":
                return session["url"]
            if session.get("subscription"):
                sub = await self.stripe("GET","subscriptions/" + session["subscription"])
                if sub["status"] not in ("canceled","incomplete_expired"):
                    portal = await self.stripe("POST","billing_portal/sessions",{"customer":customer,"return_url":target,"configuration":os.environ["STRIPE_PORTAL_CONFIG_ID"]})
                    return portal["url"]
        fields = {"mode":"subscription","line_items[0][price]":self.price,"line_items[0][quantity]":"1",
                  "payment_method_types[0]":"card","customer":customer,"client_reference_id":uid,
                  "success_url":target,"cancel_url":target}
        session = await self.stripe("POST","checkout/sessions",fields,self.space+uid+str(previous)+"checkout")
        self.save("UPDATE members SET session=? WHERE space=? AND uid=?",session["id"],self.space,uid)
        return session["url"]

    async def sync_one(self,guild,uid,customer,session_id,until,managed):
        session = await self.stripe("GET","checkout/sessions/" + session_id,{"expand[]":"subscription.latest_invoice"})
        if session["customer"] != customer or session["client_reference_id"] != uid or session["livemode"] != self.live:
            raise RuntimeError("Association Stripe incompatible")
        sub = session.get("subscription")
        if isinstance(sub,dict) and sub["customer"] == customer:
            until = max(until,paid_end(sub.get("latest_invoice"),self.price))
            self.save("UPDATE members SET paid_until=? WHERE space=? AND uid=?",until,self.space,uid)
        if not managed and until <= time.time():
            return
        try:
            member = await guild.fetch_member(int(uid))
        except discord.NotFound:
            return
        change = role_change(until,time.time(),self.role in member.roles,managed)
        if change == "grant":
            if not any(r.name == "Membre confirmé" for r in member.roles):
                return
            self.save("UPDATE members SET managed=1 WHERE space=? AND uid=?",self.space,uid)
            await member.add_roles(self.role,reason="Période Stripe payée")
        elif change == "revoke":
            if self.role in member.roles:
                await member.remove_roles(self.role,reason="Fin de la période Stripe payée")
            self.save("UPDATE members SET managed=0 WHERE space=? AND uid=?",self.space,uid)

    async def reconcile(self,guild):
        while not self.client.is_closed():
            rows = self.db.execute("SELECT uid,customer,session,paid_until,managed FROM members WHERE space=? AND session IS NOT NULL",(self.space,)).fetchall()
            for row in rows:
                try:
                    async with self.lock:
                        await self.sync_one(guild,*row)
                except Exception as exc:
                    LOG.warning("Synchronisation à reprendre (%s)",type(exc).__name__)
            await asyncio.sleep(30)
