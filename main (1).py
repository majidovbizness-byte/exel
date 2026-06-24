import asyncio, logging, datetime
from typing import Any, Callable
from aiogram import BaseMiddleware, Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import TelegramObject
from sqlalchemy import select

from database import Session, init_db, settings
from models import Organization, Subscription, SubPlan, SubStatus, User, UserRole
import services as svc
from handlers import router

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
log = logging.getLogger(__name__)

# ── Middleware ────────────────────────────────────────────────

class AuthMiddleware(BaseMiddleware):
    OPEN = {"/start"}
    async def __call__(self, handler: Callable, event: TelegramObject, data: dict[str, Any]) -> Any:
        async with Session() as session:
            data["session"] = session
            tg_user = data.get("event_from_user")
            text = getattr(getattr(event, "message", None), "text", None)
            if tg_user and text not in self.OPEN:
                r = await session.execute(select(User).where(User.telegram_id == tg_user.id))
                user = r.scalar_one_or_none()
                data["db_user"] = user
                if user:
                    user.last_seen = datetime.datetime.now(datetime.timezone.utc)
                    await session.commit()
                    msg = getattr(event,"message",None) or getattr(getattr(event,"callback_query",None),"message",None)
                    if not user.is_active:
                        if msg: await msg.answer("🔴 Hisobingiz bloklangan.")
                        return
                    if user.is_frozen:
                        if msg: await msg.answer("⏸ Hisobingiz tekshiruv rejimida.")
                        return
            else:
                data["db_user"] = None
            return await handler(event, data)

# ── Bootstrap ─────────────────────────────────────────────────

async def bootstrap():
    async with Session() as s:
        r = await s.execute(select(User).where(User.telegram_id == settings.SUPER_ADMIN_ID))
        if r.scalar_one_or_none(): return
        r2 = await s.execute(select(Organization).where(Organization.name == settings.ORG_NAME))
        org = r2.scalar_one_or_none()
        if not org:
            org = Organization(name=settings.ORG_NAME, object_text=settings.ORG_OBJECT)
            s.add(org); await s.flush()
            s.add(Subscription(organization_id=org.id, plan=SubPlan.PREMIUM, status=SubStatus.ACTIVE))
        await svc.ensure_default_plans(s, org.id)
        u = User(telegram_id=settings.SUPER_ADMIN_ID, phone="",
                 full_name="Bosh administrator", username="superadmin",
                 organization_id=org.id, role=UserRole.SUPER_ADMIN, is_active=True)
        u.set_pw("admin123")
        s.add(u); await s.commit()
        log.info("Bosh administrator yaratildi (org_id=%s)", org.id)

# ── Kunlik brifing ─────────────────────────────────────────────

async def daily_briefing(bot: Bot):
    while True:
        now = datetime.datetime.now()
        next_run = now.replace(hour=8, minute=0, second=0, microsecond=0)
        if now >= next_run:
            next_run += datetime.timedelta(days=1)
        await asyncio.sleep((next_run - now).total_seconds())
        if not settings.GEMINI_API_KEY: continue
        try:
            async with Session() as s:
                r = await s.execute(select(Organization))
                for org in r.scalars().all():
                    sub = await svc.get_sub(s, org.id)
                    if not sub: continue
                    cfg = await svc.get_plan_cfg(s, org.id, sub.plan)
                    if not cfg or not cfg.allow_ai_briefing: continue
                    today = datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
                    from sqlalchemy import func
                    from models import Nakladnaya
                    rc = await s.execute(select(func.count()).select_from(Nakladnaya).where(
                        Nakladnaya.organization_id==org.id, Nakladnaya.created_at>=today))
                    briefing = await svc.ai_briefing({
                        "sana": datetime.datetime.now().strftime("%d.%m.%Y"),
                        "nakladnoylar": rc.scalar_one(),
                    })
                    admins = await s.execute(select(User).where(
                        User.organization_id==org.id, User.is_active==True))
                    for adm in admins.scalars():
                        if adm.role.value not in("admin","super_admin"): continue
                        try: await bot.send_message(adm.telegram_id,f"<b>Kunlik brifing</b>\n\n{briefing}",parse_mode="HTML")
                        except: pass
        except Exception as e: log.error("Brifing xato: %s", e)

# ── Main ───────────────────────────────────────────────────────

async def main():
    await init_db()
    await bootstrap()
    bot = Bot(token=settings.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())
    dp.update.outer_middleware(AuthMiddleware())
    dp.include_router(router)
    log.info("Bot ishga tushdi ✅")
    await bot.delete_webhook(drop_pending_updates=True)
    asyncio.create_task(daily_briefing(bot))
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
