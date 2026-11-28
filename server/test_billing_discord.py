import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from billing_discord import Billing, paid_end


class AccessTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.role = object()
        self.bot = MagicMock(price="p", live=False, role=self.role)
        self.guild = MagicMock()
        self.member = MagicMock()
        self.member.add_roles = AsyncMock()
        self.member.remove_roles = AsyncMock()
        self.member.roles = [MagicMock()]
        self.member.roles[0].name = "Membre confirmé"
        self.guild.fetch_member = AsyncMock(return_value=self.member)
        self.invoice = {"status":"paid","amount_paid":3900,"lines":{"data":[{
            "price":{"id":"p"},"amount":3900,"type":"subscription","period":{"end":200}}]}}
        self.session = {"client_reference_id":"89","customer":"c","livemode":False,
                        "subscription":{"customer":"c","latest_invoice":self.invoice,"cancel_at_period_end":True}}
        self.bot.stripe = AsyncMock(return_value=self.session)

    async def sync(self,now,until,managed):
        with patch("billing_discord.time.time",return_value=now):
            await Billing.sync_one(self.bot,self.guild,"89","c","s",until,managed)

    async def test_payment_then_cancellation(self):
        await self.sync(100,0,False)
        self.member.add_roles.assert_awaited_once()
        self.member.roles.append(self.role)
        await self.sync(199,200,True)
        self.member.remove_roles.assert_not_awaited()
        await self.sync(200,200,True)
        self.member.remove_roles.assert_awaited_once_with(self.role,reason="Fin de la période Stripe payée")

    async def test_unpaid(self):
        self.invoice["status"]="open"
        await self.sync(100,0,False)
        self.member.add_roles.assert_not_awaited()

    async def test_gift_preserved(self):
        self.member.roles.append(self.role)
        await self.sync(201,0,False)
        self.member.remove_roles.assert_not_awaited()

    async def test_wrong_identity(self):
        self.session["client_reference_id"]="90"
        with self.assertRaises(RuntimeError):
            await self.sync(100,0,False)
        self.member.add_roles.assert_not_awaited()

    def test_other_product(self):
        self.assertEqual(paid_end(self.invoice,"different"),0)
