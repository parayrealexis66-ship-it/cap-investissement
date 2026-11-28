"""Run with discord.py >=2.4,<3 on a continuous host using the existing bot secrets."""
import re
import logging
import os

import discord

from member_access import ACCEPTED, RULES, key

GUILD_ID = int(os.environ["GUILD"])
log = logging.getLogger(__name__)


def unique_named(items, name):
    matches = [item for item in items if key(item.name) == key(name)]
    if len(matches) != 1:
        raise RuntimeError("Configuration du rôle ou du salon ambiguë")
    return matches[0]


class Confirmation(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="J’ai lu et j’accepte", style=discord.ButtonStyle.success,
                       custom_id="cap:rules:accept:v1")
    async def accept(self, interaction, button):
        await interaction.response.defer(ephemeral=True, thinking=True)
        guild = interaction.guild
        if not guild or guild.id != GUILD_ID or interaction.channel_id != client.welcome_id:
            await interaction.followup.send("Utilise le bouton dans Commencer ici.", ephemeral=True)
            return
        if interaction.message.id != client.rules_id:
            await interaction.followup.send("Utilise le bouton du règlement actuel.", ephemeral=True)
            return
        try:
            role = unique_named(await guild.fetch_roles(), "Membre confirmé")
            if role.managed or role.permissions.value:
                raise RuntimeError("Rôle incompatible")
            await interaction.user.add_roles(role, reason="Règlement accepté dans Commencer ici")
        except (discord.HTTPException, RuntimeError):
            await interaction.followup.send("Validation indisponible. Réponds au règlement avec « oui je confirme » en mentionnant le bot.", ephemeral=True)
            return
        await interaction.followup.send("Bienvenue ! Ton espace gratuit est ouvert. Tu peux rejoindre Échanges.", ephemeral=True)


class Client(discord.Client):
    welcome_id = None
    rules_id = None

    async def confirm_member(self, member):
        role = unique_named(member.guild.roles, "Membre confirmé")
        if role.managed or role.permissions.value:
            raise RuntimeError("Rôle incompatible")
        if role not in member.roles:
            await member.add_roles(role, reason="Règlement accepté dans Commencer ici")

    async def on_raw_reaction_add(self, event):
        if (event.guild_id == GUILD_ID and event.message_id == self.rules_id
                and str(event.emoji) == "✅" and event.member and not event.member.bot):
            await self.confirm_member(event.member)

    async def on_message(self, message):
        if (message.channel.id != self.welcome_id or message.author.bot
                or message.type not in (discord.MessageType.default, discord.MessageType.reply)):
            return
        answer = re.sub(r"<@!?" + str(self.user.id) + r">", "", message.content)
        if key(answer) in ACCEPTED:
            await self.confirm_member(message.author)
        elif (message.content and message.author.id != message.guild.owner_id
                and not message.author.guild_permissions.manage_messages
                and message.channel.permissions_for(message.guild.me).manage_messages):
            await message.delete()

    async def setup_hook(self):
        self.add_view(Confirmation())
        self.billing = None
        if os.environ.get("STRIPE_SECRET_KEY"):
            from billing_discord import Billing
            self.billing = Billing(self, GUILD_ID)
            self.add_view(self.billing)

    async def on_ready(self):
        guild = self.get_guild(GUILD_ID)
        if guild is None:
            raise RuntimeError("Serveur configuré indisponible")
        channel = unique_named(guild.text_channels, "commencer ici")
        async for message in channel.history(limit=None):
            if message.author.id == self.user.id and message.content == RULES:
                self.welcome_id = channel.id
                self.rules_id = message.id
                await message.edit(view=Confirmation())
                log.info("Bouton de confirmation disponible")
                if self.billing:
                    await self.billing.start(guild)
                return
        raise RuntimeError("Règlement introuvable")


if __name__ == "__main__":
    client = Client(intents=discord.Intents(guilds=True, guild_messages=True, guild_reactions=True, message_content=True))
    client.run(os.environ["BOT_TOKEN"])
