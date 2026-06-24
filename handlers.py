"""Barcha handlerlar — auth, nakladnoy, admin, calculator, OCR, menyu."""
import ast, math, operator, random, re, datetime as dt
from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    BufferedInputFile, CallbackQuery, FSInputFile, Message,
    InlineKeyboardButton as IB, InlineKeyboardMarkup as IM
)
from sqlalchemy import func, select

import services as svc
from keyboards import (
    Reg, Nak, OCR, Calc, PwChange, AdminUser, AdminVeh, AdminMat,
    AdminPlan, AdminSub, AdminObj, TEMPLATES_NAMES,
    rm, contact_kb, main_menu, doc_type_kb, skip_kb, units_kb, search_kb,
    more_kb, template_kb, format_kb, confirm_kb, plans_kb, nak_view_kb,
    calc_mode_kb, admin_kb, users_kb, mat_kb, plan_edit_kb,
    formats_kb, funcs_kb, ai_kb, back_kb, pw_kb, ocr_confirm_kb
)
from models import (
    AllowedPhone, AuditLog, Material, Nakladnaya, NakItem,
    Organization, SubPlan, Subscription, SubStatus, User, UserRole, Vehicle
)

router = Router(name="all")
BLANK = "________________________"

def _norm(phone): d=re.sub(r"\D","",phone); return d[-9:] if len(d)>=9 else d
def _blank(txt): return BLANK if not txt or set(txt.strip()).issubset({"_"," ","-"}) else txt.strip()
def _adm(u): return u.role in(UserRole.ADMIN,UserRole.SUPER_ADMIN)

# ══════════════════════════════════════════════════════════════
# AUTH — Ro'yxatdan o'tish
# ══════════════════════════════════════════════════════════════

@router.message(CommandStart())
async def cmd_start(msg: Message, state: FSMContext, session, db_user):
    if db_user and db_user.is_active and db_user.pw_hash:
        cfg = await svc.current_cfg(session, db_user.organization_id)
        await msg.answer("🏠 <b>Asosiy menyu</b>",
                         reply_markup=main_menu(db_user.role, cfg.allow_ocr if cfg else False),
                         parse_mode="HTML"); return
    await state.clear(); await state.set_state(Reg.phone)
    await msg.answer(
        "🏭 <b>Sklad Nakladnoy Tizimi</b>\n\nKirish uchun telefon raqamingizni yuboring 👇",
        parse_mode="HTML")
    await msg.answer("📱 <b>Telefon raqamni tasdiqlang:</b>",
                     reply_markup=contact_kb(), parse_mode="HTML")

@router.message(Reg.phone, F.contact)
async def got_phone(msg: Message, state: FSMContext, session):
    c=msg.contact
    if c.user_id and c.user_id!=msg.from_user.id:
        await msg.answer("Faqat o'zingizning kontaktingizni yuboring.", reply_markup=contact_kb()); return
    pn=_norm(c.phone_number)
    r=await session.execute(select(AllowedPhone))
    matched=next((a for a in r.scalars() if _norm(a.phone_number)==pn),None)
    if not matched:
        await msg.answer("🚫 Sizning raqamingiz tizimda yo'q.\nAdministratorga murojaat qiling.",
                         reply_markup=rm(), parse_mode="HTML"); await state.clear(); return
    await state.update_data(phone=c.phone_number, org_id=matched.organization_id,
                            role=matched.role.value, position=matched.position)
    await state.set_state(Reg.full_name)
    await msg.answer("👤 <b>To'liq ism-familiyangizni kiriting:</b>",
                     reply_markup=rm(), parse_mode="HTML")

@router.message(Reg.phone)
async def phone_bad(msg: Message):
    await msg.answer("📱 Telefon tugmasini bosing:", reply_markup=contact_kb())

@router.message(Reg.full_name)
async def got_name(msg: Message, state: FSMContext):
    if len(msg.text.strip())<3:
        await msg.answer("❌ Kamida 3 ta belgi kiriting."); return
    await state.update_data(full_name=msg.text.strip()); await state.set_state(Reg.password)
    await msg.answer("🔐 <b>Parol o'rnating (kamida 6 belgi):</b>", parse_mode="HTML")

@router.message(Reg.password)
async def got_pw(msg: Message, state: FSMContext):
    pw=msg.text.strip(); await msg.delete()
    if len(pw)<6: await msg.answer("❌ Parol kamida 6 belgi bo'lishi kerak."); return
    await state.update_data(pw=pw); await state.set_state(Reg.confirm_pw)
    await msg.answer("🔐 <b>Parolni tasdiqlang:</b>", parse_mode="HTML")

@router.message(Reg.confirm_pw)
async def confirm_pw(msg: Message, state: FSMContext, session):
    await msg.delete(); data=await state.get_data()
    if msg.text.strip()!=data["pw"]:
        await msg.answer("❌ Parollar mos kelmadi. Qaytadan kiriting."); return
    tg=msg.from_user; uname=User.gen_username(data["full_name"],tg.id)
    r=await session.execute(select(User).where(User.username==uname))
    if r.scalar_one_or_none(): uname=f"{uname}_{tg.id%999}"
    user=User(telegram_id=tg.id,phone=data["phone"],full_name=data["full_name"],
              username=uname,role=data["role"],organization_id=data["org_id"],
              position=data.get("position",""),is_active=True)
    user.set_pw(data["pw"]); session.add(user); await session.flush()
    await svc.audit_log(session,user.id,data["org_id"],"register",uname)
    sub=await svc.get_sub(session,data["org_id"])
    if not sub:
        session.add(Subscription(organization_id=data["org_id"],plan=SubPlan.BASIC,status=SubStatus.TRIAL))
    await svc.ensure_default_plans(session,data["org_id"]); await session.commit(); await state.clear()
    await msg.answer(
        f"✅ <b>Ro'yxatdan o'tish muvaffaqiyatli!</b>\n\n"
        f"👤 Ism: <b>{data['full_name']}</b>\n🔑 Login: <code>{uname}</code>\n"
        f"📱 Telefon: <b>{data['phone']}</b>\n\nEndi obuna tanlang 👇", parse_mode="HTML")
    cfgs=await svc.get_all_cfgs(session,data["org_id"])
    if cfgs: await msg.answer("💳 <b>Tarif tanlang:</b>",reply_markup=plans_kb(cfgs),parse_mode="HTML")

@router.callback_query(F.data.startswith("plan:"))
async def plan_chosen(cb: CallbackQuery, session, db_user):
    if not db_user: await cb.answer(); return
    plan=SubPlan(cb.data.split(":",1)[1])
    sub=await svc.get_sub(session,db_user.organization_id)
    if sub: sub.plan=plan; sub.status=SubStatus.TRIAL; sub.docs_used=0
    else: session.add(Subscription(organization_id=db_user.organization_id,plan=plan,status=SubStatus.TRIAL))
    await session.commit()
    cfg=await svc.get_plan_cfg(session,db_user.organization_id,plan)
    await cb.message.edit_text(f"✅ <b>{cfg.name if cfg else plan.value}</b> tarifi tanlandi!",parse_mode="HTML")
    await cb.message.answer("🏠 <b>Asosiy menyu</b>",
                            reply_markup=main_menu(db_user.role,cfg.allow_ocr if cfg else False),
                            parse_mode="HTML"); await cb.answer()

# ══════════════════════════════════════════════════════════════
# MENYU — Sozlamalar, tarix, parol
# ══════════════════════════════════════════════════════════════

@router.message(F.text=="⚙️ Sozlamalar")
async def settings(msg: Message, session, db_user):
    sub=await svc.get_sub(session,db_user.organization_id)
    cfg=await svc.current_cfg(session,db_user.organization_id)
    ROLES={"super_admin":"👑 Bosh admin","admin":"🛠 Admin","manager":"📊 Rahbar","employee":"👷 Xodim"}
    STATUS={"active":"✅ Faol","trial":"🔸 Sinov","expired":"❌ Tugagan"}
    plan=cfg.name if cfg else "—"; status=STATUS.get(sub.status.value if sub else "","—")
    used=sub.docs_used if sub else 0; limit="∞" if(cfg and cfg.unlimited) else(cfg.doc_limit if cfg else "—")
    seen=db_user.last_seen.strftime("%d.%m %H:%M") if db_user.last_seen else "—"
    await msg.answer(
        f"⚙️ <b>Sozlamalar</b>\n\n👤 {db_user.full_name}\n🔑 <code>{db_user.username}</code>\n"
        f"📱 {db_user.phone}\n🔐 {ROLES.get(db_user.role.value,db_user.role.value)}\n"
        f"📊 {plan} ({status})\n📄 {used}/{limit} ta\n👁 {seen}",
        reply_markup=pw_kb(), parse_mode="HTML")

@router.callback_query(F.data=="pw:change")
async def pw_start(cb: CallbackQuery, state: FSMContext):
    await state.set_state(PwChange.old_pw)
    await cb.message.edit_text("🔑 Eski parolni kiriting:"); await cb.answer()

@router.message(PwChange.old_pw)
async def pw_old(msg: Message, state: FSMContext, db_user):
    await msg.delete()
    if not db_user.check_pw(msg.text.strip()): await msg.answer("❌ Eski parol noto'g'ri."); return
    await state.set_state(PwChange.new_pw); await msg.answer("🔑 Yangi parolni kiriting:")

@router.message(PwChange.new_pw)
async def pw_new(msg: Message, state: FSMContext):
    await msg.delete()
    if len(msg.text.strip())<6: await msg.answer("❌ Kamida 6 belgi."); return
    await state.update_data(new_pw=msg.text.strip()); await state.set_state(PwChange.confirm)
    await msg.answer("🔑 Yangi parolni tasdiqlang:")

@router.message(PwChange.confirm)
async def pw_confirm(msg: Message, state: FSMContext, session, db_user):
    await msg.delete(); data=await state.get_data()
    if msg.text.strip()!=data["new_pw"]: await msg.answer("❌ Mos kelmadi."); return
    db_user.set_pw(data["new_pw"]); await session.commit(); await state.clear()
    cfg=await svc.current_cfg(session,db_user.organization_id)
    await msg.answer("✅ Parol o'zgartirildi.",reply_markup=main_menu(db_user.role,cfg.allow_ocr if cfg else False))

@router.message(F.text=="📜 Tarixim")
async def history(msg: Message, session, db_user):
    r=await session.execute(select(Nakladnaya).where(Nakladnaya.creator_id==db_user.id)
                            .order_by(Nakladnaya.created_at.desc()).limit(15))
    docs=r.scalars().all()
    if not docs: await msg.answer("📭 Hali nakladnoy yo'q."); return
    lines=["📜 <b>So'nggi 15 ta nakladnoy:</b>\n"]
    for d in docs:
        date_s=d.created_at.strftime("%d.%m.%Y") if d.created_at else ""
        icon="✅" if d.status.value=="received" else "📄"
        src="📸" if d.source=="ocr" else ""
        lines.append(f"{icon}{src} <b>№{d.number}</b> — {date_s} | {len(d.items)} ta\n")
    await msg.answer("".join(lines), parse_mode="HTML")
    cfg=await svc.current_cfg(session,db_user.organization_id)
    if docs:
        last=docs[0]; org=await session.get(Organization,last.organization_id)
        png=svc.build_preview(last,org.name if org else "")
        await msg.answer_photo(BufferedInputFile(png,"last.png"),
                               caption=f"🖼 <b>№{last.number}</b>",parse_mode="HTML",
                               reply_markup=nak_view_kb(last.id,cfg))

# ══════════════════════════════════════════════════════════════
# NAKLADNOY — Yaratish
# ══════════════════════════════════════════════════════════════

@router.message(F.text=="🆕 Yangi nakladnoy")
async def nak_start(msg: Message, state: FSMContext, session, db_user):
    if not db_user or not db_user.organization_id:
        await msg.answer("Tizimga kirish kerak. /start yuboring."); return
    sub=await svc.get_sub(session,db_user.organization_id)
    cfg=await svc.current_cfg(session,db_user.organization_id)
    if sub and cfg:
        ok,reason=sub.can_create(cfg)
        if not ok:
            await msg.answer("⛔ <b>Obuna limiti tugadi</b>\nAdministratorga murojaat qiling.",parse_mode="HTML"); return
    await state.clear(); await state.update_data(items=[])
    await state.set_state(Nak.doc_type)
    await msg.answer("📄 <b>Hujjat turini tanlang:</b>",reply_markup=doc_type_kb(),parse_mode="HTML")

@router.callback_query(Nak.doc_type, F.data.startswith("dt:"))
async def nak_dt(cb: CallbackQuery, state: FSMContext, session, db_user):
    await state.update_data(doc_type=cb.data.split(":",1)[1])
    org=await session.get(Organization,db_user.organization_id)
    prev=org.object_text if org else "—"
    await state.set_state(Nak.obj)
    await cb.message.edit_text(f"🏗 <b>Obyekt nomini kiriting:</b>\n<i>(Oldingi: {prev})</i>\n«.» yuborsangiz oldingi saqlanadi",parse_mode="HTML"); await cb.answer()

@router.message(Nak.obj)
async def nak_obj(msg: Message, state: FSMContext, session, db_user):
    txt=msg.text.strip()
    if txt==".":
        org=await session.get(Organization,db_user.organization_id)
        txt=org.object_text if org else BLANK
    await state.update_data(obj=_blank(txt)); await state.set_state(Nak.sender)
    await msg.answer("👤 <b>Jo'natuvchi (F.I.Sh / lavozim):</b>\nBo'sh: <code>___</code>",parse_mode="HTML")

@router.message(Nak.sender)
async def nak_sender(msg: Message, state: FSMContext):
    await state.update_data(sender=_blank(msg.text)); await state.set_state(Nak.receiver)
    await msg.answer("👤 <b>Qabul qiluvchi:</b>\nBo'sh: <code>___</code>",parse_mode="HTML")

@router.message(Nak.receiver)
async def nak_receiver(msg: Message, state: FSMContext):
    await state.update_data(receiver=_blank(msg.text)); await state.set_state(Nak.vehicle)
    await msg.answer("🚛 <b>Mashina davlat raqami:</b>",reply_markup=skip_kb("veh"),parse_mode="HTML")

@router.callback_query(Nak.vehicle, F.data.in_({"veh","veh_blank"}))
async def nak_veh_skip(cb: CallbackQuery, state: FSMContext):
    blank=cb.data=="veh_blank"
    await state.update_data(veh_plate=BLANK if blank else "",veh_model=BLANK if blank else "",driver=BLANK if blank else "")
    await state.set_state(Nak.destination)
    await cb.message.edit_text("📍 <b>Qayerga yuboriladi?</b>",parse_mode="HTML"); await cb.answer()

@router.message(Nak.vehicle)
async def nak_veh(msg: Message, state: FSMContext, session, db_user):
    plate=msg.text.strip(); await state.update_data(veh_plate=plate)
    r=await session.execute(select(Vehicle).where(Vehicle.organization_id==db_user.organization_id,Vehicle.plate==plate))
    veh=r.scalar_one_or_none()
    if veh:
        await state.update_data(veh_model=veh.model,driver=veh.driver)
        await state.set_state(Nak.destination)
        await msg.answer(f"✅ {veh.model}, haydovchi: {veh.driver}",parse_mode="HTML")
        await msg.answer("📍 <b>Qayerga yuboriladi?</b>",reply_markup=skip_kb("dest"),parse_mode="HTML")
    else:
        await state.set_state(Nak.veh_model)
        await msg.answer("🚛 <b>Mashina rusumi (Kamaz 6520):</b>",reply_markup=skip_kb("vmodel"),parse_mode="HTML")

@router.callback_query(Nak.veh_model, F.data.in_({"vmodel","vmodel_blank"}))
async def nak_vmodel_skip(cb: CallbackQuery, state: FSMContext):
    await state.update_data(veh_model=BLANK if cb.data=="vmodel_blank" else "")
    await state.set_state(Nak.driver)
    await cb.message.edit_text("👨‍✈️ <b>Haydovchi F.I.Sh:</b>",parse_mode="HTML"); await cb.answer()

@router.message(Nak.veh_model)
async def nak_vmodel(msg: Message, state: FSMContext):
    await state.update_data(veh_model=_blank(msg.text)); await state.set_state(Nak.driver)
    await msg.answer("👨‍✈️ <b>Haydovchi F.I.Sh:</b>",reply_markup=skip_kb("drv"),parse_mode="HTML")

@router.callback_query(Nak.driver, F.data.in_({"drv","drv_blank"}))
async def nak_drv_skip(cb: CallbackQuery, state: FSMContext, session, db_user):
    await state.update_data(driver=BLANK if cb.data=="drv_blank" else "")
    await _save_veh(state,session,db_user); await state.set_state(Nak.destination)
    await cb.message.edit_text("📍 <b>Qayerga yuboriladi?</b>",reply_markup=skip_kb("dest"),parse_mode="HTML"); await cb.answer()

@router.message(Nak.driver)
async def nak_driver(msg: Message, state: FSMContext, session, db_user):
    await state.update_data(driver=_blank(msg.text)); await _save_veh(state,session,db_user)
    await state.set_state(Nak.destination)
    await msg.answer("📍 <b>Qayerga yuboriladi?</b>",reply_markup=skip_kb("dest"),parse_mode="HTML")

async def _save_veh(state,session,db_user):
    data=await state.get_data(); plate=data.get("veh_plate","")
    if plate and plate!=BLANK:
        r=await session.execute(select(Vehicle).where(Vehicle.organization_id==db_user.organization_id,Vehicle.plate==plate))
        if not r.scalar_one_or_none():
            session.add(Vehicle(organization_id=db_user.organization_id,plate=plate,
                                model=data.get("veh_model",""),driver=data.get("driver",""))); await session.commit()

@router.callback_query(Nak.destination, F.data.in_({"dest","dest_blank"}))
async def nak_dest_skip(cb: CallbackQuery, state: FSMContext):
    await state.update_data(dest=BLANK if cb.data=="dest_blank" else "")
    await _ask_item(cb.message,state); await cb.answer()

@router.message(Nak.destination)
async def nak_dest(msg: Message, state: FSMContext):
    await state.update_data(dest=_blank(msg.text)); await _ask_item(msg,state)

async def _ask_item(msg,state):
    data=await state.get_data(); count=len(data.get("items",[]))
    await state.set_state(Nak.item)
    await msg.answer(f"📦 <b>Mahsulot qo'shing</b>\n\nKod yozing (masalan <code>22551</code>) yoki nom yozing\nQo'shildi: <b>{count} ta</b>",parse_mode="HTML")

@router.message(Nak.item)
async def nak_item(msg: Message, state: FSMContext, session, db_user):
    txt=msg.text.strip()
    if txt.replace(" ","").isdigit():
        m=await svc.mat_by_code(session,db_user.organization_id,txt)
        if m:
            await state.update_data(p_code=m.code,p_name=m.name,p_unit=m.unit)
            await state.set_state(Nak.item_qty)
            await msg.answer(f"✅ <b>{m.name}</b> ({m.unit})\n\nMiqdorini kiriting:",parse_mode="HTML"); return
    results=await svc.mat_search(session,db_user.organization_id,txt)
    if results:
        await state.set_state(Nak.item_search)
        await msg.answer(f"🔍 <b>«{txt}» natijalari:</b>",reply_markup=search_kb(results),parse_mode="HTML"); return
    cfg=await svc.current_cfg(session,db_user.organization_id)
    from database import settings as _s
    if cfg and cfg.allow_ai_search and _s.GEMINI_API_KEY:
        wait=await msg.answer("🤖 AI qidiryapti...")
        try:
            r=await session.execute(select(Material).where(Material.organization_id==db_user.organization_id).limit(200))
            all_m=[{"code":m.code,"name":m.name,"unit":m.unit} for m in r.scalars()]
            ai_r=await svc.ai_search(txt,all_m)
            await wait.delete()
            if ai_r:
                from models import Material as _Mat
                ai_mats=[m for mr in ai_r for m in [await svc.mat_by_code(session,db_user.organization_id,mr.get("code",""))] if m]
                if ai_mats:
                    await state.set_state(Nak.item_search)
                    await msg.answer(f"🤖 <b>AI topdi:</b>",reply_markup=search_kb(ai_mats),parse_mode="HTML"); return
        except: 
            try: await wait.delete()
            except: pass
    await state.update_data(p_code="",p_name=txt); await state.set_state(Nak.item_unit)
    await msg.answer(f"«{txt}» bazada topilmadi. Birligini tanlang:",reply_markup=units_kb())

@router.callback_query(Nak.item_search, F.data.startswith("mat:"))
async def nak_pick(cb: CallbackQuery, state: FSMContext, session):
    val=cb.data.split(":",1)[1]
    if val=="manual":
        await state.set_state(Nak.item); await cb.message.edit_text("Mahsulot nomini yozing:"); await cb.answer(); return
    m=await svc.mat_get(session,int(val))
    if not m: await cb.answer("Topilmadi.",show_alert=True); return
    await state.update_data(p_code=m.code,p_name=m.name,p_unit=m.unit); await state.set_state(Nak.item_qty)
    await cb.message.edit_text(f"✅ <b>{m.name}</b> ({m.unit})\n\nMiqdorini kiriting:",parse_mode="HTML"); await cb.answer()

@router.callback_query(Nak.item_unit, F.data.startswith("unit:"))
async def nak_unit(cb: CallbackQuery, state: FSMContext):
    await state.update_data(p_unit=cb.data.split(":",1)[1]); await state.set_state(Nak.item_qty)
    await cb.message.edit_text("🔢 <b>Miqdor kiriting:</b>",parse_mode="HTML"); await cb.answer()

@router.message(Nak.item_qty)
async def nak_qty(msg: Message, state: FSMContext):
    data=await state.get_data(); items=data.get("items",[])
    items.append({"code":data.get("p_code",""),"name":data.get("p_name",""),
                  "unit":data.get("p_unit",""),"qty":msg.text.strip()})
    await state.update_data(items=items)
    await state.set_state(Nak.more)
    summary="\n".join(f"  {i+1}. {it['name']} — {it['qty']} {it['unit']}" for i,it in enumerate(items))
    await msg.answer(f"✅ <b>Qo'shildi!</b>\n\n📋 <b>Ro'yxat:</b>\n{summary}",
                     reply_markup=more_kb(len(items)),parse_mode="HTML")

@router.callback_query(Nak.more, F.data=="more:yes")
async def nak_more(cb: CallbackQuery, state: FSMContext):
    await _ask_item(cb.message,state); await cb.answer()

@router.callback_query(Nak.more, F.data=="more:no")
async def nak_done(cb: CallbackQuery, state: FSMContext, session, db_user):
    data=await state.get_data()
    if not data.get("items"): await cb.answer("Kamida 1 ta mahsulot!",show_alert=True); return
    cfg=await svc.current_cfg(session,db_user.organization_id)
    max_t=cfg.allow_templates if cfg else 2
    from database import settings as _s
    sug=""; sug_tpl=1
    if cfg and cfg.allow_ai_search and _s.GEMINI_API_KEY:
        try:
            sug_tpl=await svc.ai_suggest_template(data["items"])
            sug=f"\n\n🤖 <i>AI tavsiya: {TEMPLATES_NAMES.get(sug_tpl,'Klassik')} (#{sug_tpl})</i>"
        except: pass
    await state.update_data(suggested_tpl=sug_tpl)
    await state.set_state(Nak.template)
    await cb.message.edit_text(f"📋 <b>Shablonni tanlang:</b>{sug}",
                               reply_markup=template_kb(max_t),parse_mode="HTML"); await cb.answer()

@router.callback_query(Nak.template, F.data.startswith("tpl:"))
async def nak_tpl(cb: CallbackQuery, state: FSMContext, session, db_user):
    await state.update_data(tpl=int(cb.data.split(":",1)[1]))
    cfg=await svc.current_cfg(session,db_user.organization_id)
    await state.set_state(Nak.fmt)
    await cb.message.edit_text("📄 <b>Fayl formatini tanlang:</b>",
                               reply_markup=format_kb(cfg),parse_mode="HTML"); await cb.answer()

@router.callback_query(Nak.fmt, F.data.startswith("fmt:"))
async def nak_fmt(cb: CallbackQuery, state: FSMContext):
    await state.update_data(fmt=cb.data.split(":",1)[1]); data=await state.get_data()
    items_text="\n".join(f"  {i+1}. {it['name']} — {it['qty']} {it['unit']}" for i,it in enumerate(data["items"]))
    veh=f"{data.get('veh_model','')} {data.get('veh_plate','')}".strip() or BLANK
    await state.set_state(Nak.confirm)
    await cb.message.edit_text(
        f"📋 <b>Tekshiring:</b>\n\n📄 {('Chiqim' if data['doc_type']=='chiqim' else 'Qaytarish')}\n"
        f"🏗 {data.get('obj',BLANK)}\n👤 {data.get('sender',BLANK)}\n👤 {data.get('receiver',BLANK)}\n"
        f"🚛 {veh}\n👨‍✈️ {data.get('driver',BLANK)}\n📍 {data.get('dest',BLANK)}\n\n"
        f"📦 <b>{len(data['items'])} ta:</b>\n{items_text}\n\nTo'g'rimi?",
        reply_markup=confirm_kb(),parse_mode="HTML"); await cb.answer()

@router.callback_query(Nak.confirm, F.data=="confirm:edit")
async def nak_edit(cb: CallbackQuery, state: FSMContext):
    await state.set_state(Nak.doc_type)
    await cb.message.edit_text("✏️ Qaytadan boshlash...")
    await cb.message.answer("📄 <b>Hujjat turini tanlang:</b>",reply_markup=doc_type_kb(),parse_mode="HTML"); await cb.answer()

@router.callback_query(Nak.confirm, F.data=="confirm:no")
async def nak_cancel(cb: CallbackQuery, state: FSMContext, session, db_user):
    await state.clear(); await cb.message.edit_text("❌ Bekor qilindi.")
    cfg=await svc.current_cfg(session,db_user.organization_id)
    await cb.message.answer("🏠 <b>Asosiy menyu</b>",
                            reply_markup=main_menu(db_user.role,cfg.allow_ocr if cfg else False),
                            parse_mode="HTML"); await cb.answer()

@router.callback_query(Nak.confirm, F.data=="confirm:yes")
async def nak_create(cb: CallbackQuery, state: FSMContext, session, db_user):
    data=await state.get_data()
    org=await session.get(Organization,db_user.organization_id)
    sub=await svc.get_sub(session,db_user.organization_id)
    cfg=await svc.current_cfg(session,db_user.organization_id)
    if sub and cfg:
        ok,reason=sub.can_create(cfg)
        if not ok:
            await cb.message.edit_text("⛔ Limit tugadi.",parse_mode="HTML"); await cb.answer(); return
    number=await svc.next_number(session,db_user.organization_id)
    pin=f"{random.randint(0,9999):04d}"
    nak=Nakladnaya(number=number,organization_id=db_user.organization_id,creator_id=db_user.id,
                   doc_type=data["doc_type"],object_text=data.get("obj",""),
                   sender=data.get("sender",""),receiver=data.get("receiver",""),
                   vehicle_plate=data.get("veh_plate",""),vehicle_model=data.get("veh_model",""),
                   driver=data.get("driver",""),destination=data.get("dest",""),
                   template_id=data.get("tpl",1),pin=pin,source="manual")
    for i,it in enumerate(data["items"],1):
        nak.items.append(NakItem(row_no=i,code=it["code"],name=it["name"],unit=it["unit"],quantity=it["qty"]))
    session.add(nak); await session.flush()
    if sub: sub.docs_used+=1
    warnings=await svc.check_suspicious(session,db_user.id,db_user.organization_id)
    for w in warnings: await svc.audit_log(session,db_user.id,db_user.organization_id,"suspicious",w,suspicious=True)
    await svc.audit_log(session,db_user.id,db_user.organization_id,"nak_create",number)
    await session.commit()
    nak.created_at=dt.datetime.now()
    await cb.message.edit_text(f"⏳ <b>№{number}</b> tayyorlanmoqda...",parse_mode="HTML")
    try:
        path=await svc.generate_doc(nak,org.name if org else "",data.get("fmt","excel"),cfg,data.get("tpl",1))
        await cb.message.answer_document(FSInputFile(path),
            caption=f"✅ <b>№{number} tayyor!</b>\n🔑 PIN: <code>{pin}</code>\nQabul: /qabul {number} {pin}",
            parse_mode="HTML")
        png=svc.build_preview(nak,org.name if org else "")
        await cb.message.answer_photo(BufferedInputFile(png,f"nak_{number.replace('/','_')}.png"),
            caption=f"🖼 <b>№{number}</b>",parse_mode="HTML",reply_markup=nak_view_kb(nak.id,cfg))
    except Exception as e:
        await cb.message.answer(f"⚠️ Fayl xato: {e}")
    await state.clear()
    cfg2=await svc.current_cfg(session,db_user.organization_id)
    await cb.message.answer("🏠 <b>Asosiy menyu</b>",
                            reply_markup=main_menu(db_user.role,cfg2.allow_ocr if cfg2 else False),
                            parse_mode="HTML"); await cb.answer()

@router.callback_query(F.data.startswith("view:"))
async def view_action(cb: CallbackQuery, session, db_user):
    parts=cb.data.split(":"); action=parts[1]; nid=int(parts[2])
    nak=await session.get(Nakladnaya,nid)
    if not nak or nak.organization_id!=db_user.organization_id:
        await cb.answer("Topilmadi.",show_alert=True); return
    org=await session.get(Organization,nak.organization_id)
    cfg=await svc.current_cfg(session,db_user.organization_id)
    org_name=org.name if org else ""
    if action=="preview":
        png=svc.build_preview(nak,org_name)
        await cb.message.answer_photo(BufferedInputFile(png,"preview.png"),
                                      caption=f"🖼 <b>№{nak.number}</b>",parse_mode="HTML")
    elif action in("excel","word","pdf"):
        path=await svc.generate_doc(nak,org_name,action,cfg,nak.template_id)
        await cb.message.answer_document(FSInputFile(path))
    elif action=="del":
        await session.delete(nak); await session.commit()
        await cb.message.edit_text("🗑 O'chirildi.")
    await cb.answer()

# ══════════════════════════════════════════════════════════════
# QABUL
# ══════════════════════════════════════════════════════════════

@router.message(F.text.startswith("/qabul"))
async def qabul(msg: Message, session, db_user):
    parts=msg.text.split()
    if len(parts)!=3: await msg.answer("Foydalanish: /qabul 0001/2026 1234"); return
    _,number,pin=parts
    r=await session.execute(select(Nakladnaya).where(
        Nakladnaya.organization_id==db_user.organization_id,Nakladnaya.number==number))
    nak=r.scalar_one_or_none()
    if not nak or nak.pin!=pin: await msg.answer("❌ PIN noto'g'ri yoki topilmadi."); return
    if nak.status.value=="received": await msg.answer(f"ℹ️ №{number} allaqachon qabul qilingan."); return
    from models import DocStatus
    nak.status=DocStatus.RECEIVED; nak.received_at=dt.datetime.now(dt.timezone.utc)
    await svc.audit_log(session,db_user.id,db_user.organization_id,"nak_receive",number)
    await session.commit()
    await msg.answer(f"✅ <b>№{number} qabul qilindi.</b>",parse_mode="HTML")

# ══════════════════════════════════════════════════════════════
# HISOBLASH
# ══════════════════════════════════════════════════════════════

_OPS={ast.Add:operator.add,ast.Sub:operator.sub,ast.Mult:operator.mul,
      ast.Div:operator.truediv,ast.Pow:operator.pow,ast.USub:operator.neg,
      ast.Mod:operator.mod,ast.FloorDiv:operator.floordiv}
_FNS={"sqrt":math.sqrt,"abs":abs,"round":round,"floor":math.floor,"ceil":math.ceil,
      "log":math.log,"log10":math.log10,"sin":math.sin,"cos":math.cos,"tan":math.tan,
      "pi":math.pi,"e":math.e,"pow":pow}

def _eval(node):
    if isinstance(node,ast.Constant): return node.value
    if isinstance(node,ast.BinOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval(node.left),_eval(node.right))
    if isinstance(node,ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval(node.operand))
    if isinstance(node,ast.Call):
        fn=node.func.id if isinstance(node.func,ast.Name) else None
        if fn in _FNS: return _FNS[fn](*[_eval(a) for a in node.args])
    if isinstance(node,ast.Name) and node.id in _FNS: return _FNS[node.id]
    raise ValueError("Ruxsat etilmagan")

def simple_calc(expr):
    try:
        e=expr.replace(",",".").replace("×","*").replace("÷","/").replace("^","**")
        res=_eval(ast.parse(e.strip(),mode="eval").body)
        if isinstance(res,float) and res.is_integer(): res=int(res)
        fmt=f"{res:,}".replace(",", " ") if isinstance(res,(int,float)) else str(res)
        return f"🧮 <code>{expr}</code>\n= <b>{fmt}</b>"
    except ZeroDivisionError: return "❌ Nolga bo'lish mumkin emas."
    except: return None

@router.message(F.text=="🧮 Hisoblash")
async def calc_open(msg: Message, state: FSMContext, session, db_user):
    cfg=await svc.current_cfg(session,db_user.organization_id)
    if cfg and not cfg.allow_calc and not cfg.allow_ai_calc:
        await msg.answer("🧮 Hisoblash tarifingizda mavjud emas."); return
    from database import settings as _s
    has_ai=bool(cfg and cfg.allow_ai_calc and _s.GEMINI_API_KEY)
    await msg.answer("🧮 <b>Hisoblash</b>\nRejimni tanlang:",
                     reply_markup=calc_mode_kb(has_ai),parse_mode="HTML")

@router.callback_query(F.data.startswith("calc:"))
async def calc_mode(cb: CallbackQuery, state: FSMContext, session, db_user):
    action=cb.data.split(":",1)[1]
    if action=="back":
        await state.clear(); await cb.message.edit_text("🏠 Asosiy menyu"); await cb.answer(); return
    if action=="simple":
        await state.update_data(calc_mode="simple"); await state.set_state(Calc.expr)
        await cb.message.edit_text(
            "🔢 <b>Oddiy hisoblash</b>\n\n<code>125 * 48</code>\n<code>sqrt(144)</code>\n<code>1500000 * 0.12</code>\n\nChiqish: /menu",
            parse_mode="HTML")
    else:
        await state.update_data(calc_mode="ai"); await state.set_state(Calc.expr)
        await cb.message.edit_text(
            "🤖 <b>AI hisoblash</b>\n\nMisol:\n<code>100 metr truba uchun har 5 metrda 1 birikma, nechta?</code>\n\nChiqish: /menu",
            parse_mode="HTML")
    await cb.answer()

@router.message(Calc.expr)
async def calc_expr(msg: Message, state: FSMContext, db_user):
    if msg.text.strip().lower() in("/menu","menu","🏠"):
        await state.clear()
        await msg.answer("🏠 <b>Asosiy menyu</b>",reply_markup=main_menu(db_user.role),parse_mode="HTML"); return
    data=await state.get_data(); mode=data.get("calc_mode","simple"); expr=msg.text.strip()
    if mode=="ai":
        from database import settings as _s
        if not _s.GEMINI_API_KEY: await msg.answer("❌ GEMINI_API_KEY sozlanmagan."); return
        wait=await msg.answer("⏳ AI hisoblayapti...")
        try:
            res=await svc.ai_calc(expr); await wait.delete()
            await msg.answer(f"🤖 <b>AI natija:</b>\n\n{res}",parse_mode="HTML")
        except Exception as e:
            await wait.delete(); await msg.answer(f"❌ AI xato: {e}")
    else:
        res=simple_calc(expr)
        if res: await msg.answer(res,parse_mode="HTML")
        else:
            from database import settings as _s
            if _s.GEMINI_API_KEY:
                wait=await msg.answer("⏳ AI hisoblayapti...")
                try:
                    ai_res=await svc.ai_calc(expr); await wait.delete()
                    await msg.answer(f"🤖 <b>AI natija:</b>\n\n{ai_res}",parse_mode="HTML")
                except: await wait.delete(); await msg.answer("❌ Noto'g'ri ifoda.",parse_mode="HTML")
            else: await msg.answer("❌ Noto'g'ri ifoda.")

# ══════════════════════════════════════════════════════════════
# OCR — Rasm → Excel
# ══════════════════════════════════════════════════════════════

@router.message(F.text=="📸 Rasm → Excel")
async def ocr_start(msg: Message, state: FSMContext, session, db_user):
    cfg=await svc.current_cfg(session,db_user.organization_id)
    if not cfg or not cfg.allow_ocr:
        await msg.answer("📸 Rasm→Excel tarifingizda mavjud emas.\nAdministratorga murojaat qiling."); return
    from database import settings as _s
    if not _s.GEMINI_API_KEY:
        await msg.answer("⚙️ GEMINI_API_KEY sozlanmagan."); return
    await state.set_state(OCR.waiting_photo)
    await msg.answer("📸 <b>Qo'lyozma nakladnoy rasmini yuboring</b>\n\nBot rasmni o'qib Excel faylga aylantiradi.",parse_mode="HTML")

@router.message(OCR.waiting_photo, F.photo)
async def ocr_photo(msg: Message, state: FSMContext, session, db_user):
    wait=await msg.answer("⏳ Rasm tahlil qilinmoqda...")
    try:
        photo=msg.photo[-1]; file=await msg.bot.get_file(photo.file_id)
        io_bytes=await msg.bot.download_file(file.file_path)
        img_data=io_bytes.read() if hasattr(io_bytes,"read") else bytes(io_bytes)
        data=await svc.ai_ocr(img_data); await state.update_data(ocr_data=data)
        await state.set_state(OCR.confirm)
        items=data.get("items",[])
        prev="\n".join(f"  {i+1}. <code>{it.get('code','—')}</code> | {it.get('name','')} — {it.get('quantity','')} {it.get('unit','')}" for i,it in enumerate(items[:15]))
        await wait.delete()
        await msg.answer(
            f"✅ <b>Rasm o'qildi — tekshiring:</b>\n\n"
            f"🏗 {data.get('object_text','—')}\n👤 {data.get('sender','—')}\n👤 {data.get('receiver','—')}\n\n"
            f"📦 <b>{len(items)} ta:</b>\n{prev}",
            reply_markup=ocr_confirm_kb(),parse_mode="HTML")
    except Exception as e:
        await wait.delete()
        await msg.answer(f"❌ Rasm o'qishda xato: {e}\nSifatliroq rasm yuboring."); await state.clear()

@router.message(OCR.waiting_photo)
async def ocr_not_photo(msg: Message):
    await msg.answer("📸 Iltimos, rasm yuboring.")

@router.callback_query(OCR.confirm, F.data=="ocr:cancel")
async def ocr_cancel(cb: CallbackQuery, state: FSMContext, session, db_user):
    await state.clear(); cfg=await svc.current_cfg(session,db_user.organization_id)
    await cb.message.edit_text("❌ Bekor qilindi.")
    await cb.message.answer("🏠 <b>Asosiy menyu</b>",
                            reply_markup=main_menu(db_user.role,cfg.allow_ocr if cfg else False),
                            parse_mode="HTML"); await cb.answer()

@router.callback_query(OCR.confirm, F.data=="ocr:confirm")
async def ocr_confirm(cb: CallbackQuery, state: FSMContext, session, db_user):
    ocr_data=(await state.get_data()).get("ocr_data",{})
    org=await session.get(Organization,db_user.organization_id)
    number=await svc.next_number(session,db_user.organization_id)
    nak=Nakladnaya(number=number,organization_id=db_user.organization_id,creator_id=db_user.id,
                   doc_type="chiqim",object_text=ocr_data.get("object_text",""),
                   sender=ocr_data.get("sender",""),receiver=ocr_data.get("receiver",""),
                   template_id=1,pin=f"{random.randint(0,9999):04d}",source="ocr")
    for i,it in enumerate(ocr_data.get("items",[]),1):
        nak.items.append(NakItem(row_no=i,code=it.get("code",""),name=it.get("name",""),
                                 unit=it.get("unit",""),quantity=it.get("quantity","")))
    session.add(nak); await session.flush()
    await svc.audit_log(session,db_user.id,db_user.organization_id,"ocr_create",number)
    await session.commit(); nak.created_at=dt.datetime.now()
    import os; from services import GEN
    xl=os.path.join(GEN,f"ocr_{number.replace('/','_')}.xlsx")
    svc.build_excel(nak,org.name if org else "",xl,1)
    await cb.message.answer_document(FSInputFile(xl),caption=f"✅ <b>OCR №{number} tayyor!</b>",parse_mode="HTML")
    png=svc.build_preview(nak,org.name if org else "")
    await cb.message.answer_photo(BufferedInputFile(png,f"ocr_{number.replace('/','_')}.png"),caption="🖼 Ko'rinishi")
    await state.clear()
    cfg=await svc.current_cfg(session,db_user.organization_id)
    await cb.message.answer("🏠 <b>Asosiy menyu</b>",
                            reply_markup=main_menu(db_user.role,cfg.allow_ocr if cfg else False),
                            parse_mode="HTML"); await cb.answer()

# ══════════════════════════════════════════════════════════════
# ADMIN PANEL
# ══════════════════════════════════════════════════════════════

@router.message(F.text=="🛠 Admin panel")
async def adm_menu(msg: Message, db_user):
    if not _adm(db_user): await msg.answer("🚫 Faqat administrator uchun."); return
    await msg.answer("🛠 <b>Administrator paneli</b>",reply_markup=admin_kb(),parse_mode="HTML")

@router.callback_query(F.data=="adm:back")
async def adm_back(cb: CallbackQuery):
    await cb.message.edit_text("🛠 <b>Administrator paneli</b>",reply_markup=admin_kb(),parse_mode="HTML"); await cb.answer()

@router.callback_query(F.data=="adm:users")
async def adm_users(cb: CallbackQuery, db_user):
    if not _adm(db_user): await cb.answer(); return
    await cb.message.edit_text("👥 <b>Foydalanuvchilar</b>",reply_markup=users_kb(),parse_mode="HTML"); await cb.answer()

@router.callback_query(F.data=="usr:add")
async def usr_add(cb: CallbackQuery, state: FSMContext, db_user):
    if not _adm(db_user): await cb.answer(); return
    await state.set_state(AdminUser.phone)
    await cb.message.edit_text("📱 Yangi xodim telefon raqami:"); await cb.answer()

@router.message(AdminUser.phone)
async def usr_add_ph(msg: Message, state: FSMContext):
    await state.update_data(phone=msg.text.strip()); await state.set_state(AdminUser.name)
    await msg.answer("👤 To'liq F.I.Sh:")

@router.message(AdminUser.name)
async def usr_add_nm(msg: Message, state: FSMContext):
    await state.update_data(name=msg.text.strip()); await state.set_state(AdminUser.position)
    await msg.answer("💼 Lavozimi (bo'sh: '.' yuboring):")

@router.message(AdminUser.position)
async def usr_add_pos(msg: Message, state: FSMContext):
    await state.update_data(position="" if msg.text.strip()=="." else msg.text.strip())
    await state.set_state(AdminUser.role)
    await msg.answer("🔑 Rolini tanlang:",reply_markup=IM(inline_keyboard=[
        [IB(text="👷 Xodim",callback_data="urole:employee")],
        [IB(text="📊 Rahbar",callback_data="urole:manager")],
        [IB(text="🛠 Administrator",callback_data="urole:admin")]]))

@router.callback_query(AdminUser.role, F.data.startswith("urole:"))
async def usr_add_role(cb: CallbackQuery, state: FSMContext, session, db_user):
    role=cb.data.split(":",1)[1]; data=await state.get_data()
    r=await session.execute(select(AllowedPhone).where(AllowedPhone.phone_number==data["phone"]))
    if r.scalar_one_or_none():
        await cb.message.edit_text("⚠️ Bu raqam allaqachon mavjud."); await state.clear(); await cb.answer(); return
    session.add(AllowedPhone(organization_id=db_user.organization_id,phone_number=data["phone"],
                             full_name=data["name"],role=UserRole(role),position=data.get("position","")))
    await svc.audit_log(session,db_user.id,db_user.organization_id,"user_add",data["phone"])
    await session.commit(); await state.clear()
    await cb.message.edit_text(f"✅ <b>{data['name']}</b> ({data['phone']}) qo'shildi.\n/start yuborsa avtomatik kiradi.",parse_mode="HTML"); await cb.answer()

@router.callback_query(F.data=="usr:list")
async def usr_list(cb: CallbackQuery, session, db_user):
    if not _adm(db_user): await cb.answer(); return
    r=await session.execute(select(User).where(User.organization_id==db_user.organization_id).order_by(User.full_name))
    users=r.scalars().all()
    if not users: await cb.message.edit_text("Xodimlar yo'q."); await cb.answer(); return
    ROLES={"super_admin":"👑","admin":"🛠","manager":"📊","employee":"👷"}
    lines=["👥 <b>Xodimlar:</b>\n"]
    for u in users:
        ico="🟢" if u.is_active and not u.is_frozen else("⏸" if u.is_frozen else "🔴")
        seen=u.last_seen.strftime("%d.%m %H:%M") if u.last_seen else "—"
        lines.append(f"{ico}{ROLES.get(u.role.value,'')} <b>{u.full_name}</b>\n   🔑{u.username} | 📱{u.phone} | 👁{seen}\n")
    await cb.message.edit_text("\n".join(lines),parse_mode="HTML",reply_markup=back_kb()); await cb.answer()

@router.callback_query(F.data.in_({"usr:block_menu","usr:unblock_menu","usr:freeze_menu"}))
async def usr_action_info(cb: CallbackQuery):
    cmds={"usr:block_menu":"/block","usr:unblock_menu":"/unblock","usr:freeze_menu":"/freeze"}
    await cb.message.edit_text(f"Telefon raqami:\n<code>{cmds[cb.data]} +998901234567</code>",parse_mode="HTML"); await cb.answer()

@router.callback_query(F.data=="usr:stats")
async def usr_stats(cb: CallbackQuery, session, db_user):
    if not _adm(db_user): await cb.answer(); return
    r=await session.execute(select(Nakladnaya.creator_id,func.count()).where(Nakladnaya.organization_id==db_user.organization_id).group_by(Nakladnaya.creator_id))
    rows=r.all(); lines=["📈 <b>Statistika (jami):</b>\n"]
    for uid,cnt in sorted(rows,key=lambda x:x[1],reverse=True):
        u=await session.get(User,uid); lines.append(f"  👤 {u.full_name if u else uid}: <b>{cnt} ta</b>")
    await cb.message.edit_text("\n".join(lines) if rows else "Ma'lumot yo'q.",parse_mode="HTML",reply_markup=back_kb()); await cb.answer()

@router.callback_query(F.data=="usr:rating")
async def usr_rating(cb: CallbackQuery, session, db_user):
    now=dt.datetime.now(); ms=now.replace(day=1,hour=0,minute=0,second=0,microsecond=0)
    r=await session.execute(select(Nakladnaya.creator_id,func.count()).where(
        Nakladnaya.organization_id==db_user.organization_id,Nakladnaya.created_at>=ms).group_by(Nakladnaya.creator_id))
    rows=sorted(r.all(),key=lambda x:x[1],reverse=True)
    medals=["🥇","🥈","🥉"]; lines=["🏆 <b>Bu oylik reyting:</b>\n"]
    for i,(uid,cnt) in enumerate(rows):
        u=await session.get(User,uid); icon=medals[i] if i<3 else f"{i+1}."
        lines.append(f"{icon} {u.full_name if u else uid}: <b>{cnt} ta</b>")
    await cb.message.edit_text("\n".join(lines) if rows else "Bu oy hali nakladnoy yo'q.",parse_mode="HTML",reply_markup=back_kb()); await cb.answer()

@router.message(Command("block"))
async def block_cmd(msg: Message, session, db_user):
    if not _adm(db_user): return
    parts=msg.text.split(maxsplit=1)
    if len(parts)!=2: await msg.answer("Foydalanish: /block <telefon>"); return
    r=await session.execute(select(User).where(User.phone==parts[1].strip()))
    u=r.scalar_one_or_none()
    if not u: await msg.answer("Topilmadi."); return
    u.is_active=False; await svc.audit_log(session,db_user.id,db_user.organization_id,"user_block",parts[1])
    await session.commit(); await msg.answer(f"🔴 <b>{u.full_name}</b> bloklandi.",parse_mode="HTML")

@router.message(Command("unblock"))
async def unblock_cmd(msg: Message, session, db_user):
    if not _adm(db_user): return
    parts=msg.text.split(maxsplit=1)
    if len(parts)!=2: await msg.answer("Foydalanish: /unblock <telefon>"); return
    r=await session.execute(select(User).where(User.phone==parts[1].strip()))
    u=r.scalar_one_or_none()
    if not u: await msg.answer("Topilmadi."); return
    u.is_active=True; u.is_frozen=False
    await svc.audit_log(session,db_user.id,db_user.organization_id,"user_unblock",parts[1])
    await session.commit(); await msg.answer(f"🟢 <b>{u.full_name}</b> blokdan chiqarildi.",parse_mode="HTML")

@router.message(Command("freeze"))
async def freeze_cmd(msg: Message, session, db_user):
    if not _adm(db_user): return
    parts=msg.text.split(maxsplit=1)
    if len(parts)!=2: await msg.answer("Foydalanish: /freeze <telefon>"); return
    r=await session.execute(select(User).where(User.phone==parts[1].strip()))
    u=r.scalar_one_or_none()
    if not u: await msg.answer("Topilmadi."); return
    u.is_frozen=True; await svc.audit_log(session,db_user.id,db_user.organization_id,"user_freeze",parts[1])
    await session.commit(); await msg.answer(f"⏸ <b>{u.full_name}</b> tekshiruv rejimiga qo'yildi.",parse_mode="HTML")

# ── Mahsulot bazasi ──

@router.callback_query(F.data=="adm:mat")
async def adm_mat(cb: CallbackQuery, db_user):
    if not _adm(db_user): await cb.answer(); return
    await cb.message.edit_text("📦 <b>Mahsulot bazasi</b>",reply_markup=mat_kb(),parse_mode="HTML"); await cb.answer()

@router.callback_query(F.data=="mat:bulk")
async def mat_bulk_start(cb: CallbackQuery, state: FSMContext, db_user):
    if not _adm(db_user): await cb.answer(); return
    await state.set_state(AdminMat.bulk)
    await cb.message.edit_text("📥 <b>Ko'plab qo'shish:</b>\n\nFormat: <code>kod;nom;birlik</code>\n\nMisol:\n<code>22551;Гайка М27;кг\n9375;Шайба М 27;кг</code>",parse_mode="HTML"); await cb.answer()

@router.message(AdminMat.bulk)
async def mat_bulk(msg: Message, state: FSMContext, session, db_user):
    added=updated=0; errors=[]
    for line in msg.text.split("\n"):
        line=line.strip()
        if not line: continue
        parts=[p.strip() for p in line.split(";")]
        if len(parts)!=3: errors.append(line); continue
        code,name,unit=parts; ex=await svc.mat_by_code(session,db_user.organization_id,code)
        if ex: ex.name=name; ex.unit=unit; updated+=1
        else: session.add(Material(organization_id=db_user.organization_id,code=code,name=name,unit=unit)); added+=1
    await svc.audit_log(session,db_user.id,db_user.organization_id,"mat_bulk",f"+{added}~{updated}")
    await session.commit(); await state.clear()
    txt=f"✅ Qo'shildi: <b>{added}</b> ta\n♻️ Yangilandi: <b>{updated}</b> ta"
    if errors: txt+=f"\n⚠️ Xato ({len(errors)}):\n"+"\n".join(errors[:5])
    await msg.answer(txt,parse_mode="HTML")

@router.callback_query(F.data=="mat:search")
async def mat_search_start(cb: CallbackQuery, state: FSMContext, db_user):
    if not _adm(db_user): await cb.answer(); return
    await state.set_state(AdminMat.search); await cb.message.edit_text("🔍 Kod yoki nom kiriting:"); await cb.answer()

@router.message(AdminMat.search)
async def mat_search_do(msg: Message, state: FSMContext, session, db_user):
    q=msg.text.strip()
    by_code=await svc.mat_by_code(session,db_user.organization_id,q)
    results=([by_code] if by_code else [])+await svc.mat_search(session,db_user.organization_id,q,15)
    await state.clear()
    if not results: await msg.answer("Hech narsa topilmadi."); return
    lines=[f"<code>{m.code or '—'}</code> | {m.name} | {m.unit}" for m in results[:15]]
    await msg.answer("\n".join(lines),parse_mode="HTML")

@router.callback_query(F.data=="mat:stats")
async def mat_stats(cb: CallbackQuery, session, db_user):
    r=await session.execute(select(func.count()).select_from(Material).where(Material.organization_id==db_user.organization_id))
    await cb.message.edit_text(f"📊 Bazada jami: <b>{r.scalar_one()} ta</b>",parse_mode="HTML",reply_markup=back_kb()); await cb.answer()

@router.callback_query(F.data=="mat:delete")
async def mat_del_info(cb: CallbackQuery):
    await cb.message.edit_text("O'chirish: <code>/ochir_kod 22551</code>",parse_mode="HTML"); await cb.answer()

@router.message(Command("ochir_kod"))
async def del_mat(msg: Message, session, db_user):
    if not _adm(db_user): return
    parts=msg.text.split(maxsplit=1)
    if len(parts)!=2: await msg.answer("/ochir_kod <kod>"); return
    m=await svc.mat_by_code(session,db_user.organization_id,parts[1])
    if not m: await msg.answer("Topilmadi."); return
    await session.delete(m); await svc.audit_log(session,db_user.id,db_user.organization_id,"mat_delete",parts[1])
    await session.commit(); await msg.answer(f"🗑 <code>{parts[1]}</code> o'chirildi.",parse_mode="HTML")

# ── Transport ──

@router.callback_query(F.data=="adm:veh")
async def adm_veh(cb: CallbackQuery, state: FSMContext, db_user):
    if not _adm(db_user): await cb.answer(); return
    await state.set_state(AdminVeh.plate); await cb.message.edit_text("🚛 Yangi mashina davlat raqami:"); await cb.answer()

@router.message(AdminVeh.plate)
async def veh_pl(msg: Message, state: FSMContext):
    await state.update_data(plate=msg.text.strip()); await state.set_state(AdminVeh.model)
    await msg.answer("🚛 Mashina rusumi:")

@router.message(AdminVeh.model)
async def veh_mod(msg: Message, state: FSMContext):
    await state.update_data(model=msg.text.strip()); await state.set_state(AdminVeh.driver)
    await msg.answer("👨‍✈️ Haydovchi F.I.Sh:")

@router.message(AdminVeh.driver)
async def veh_drv(msg: Message, state: FSMContext, session, db_user):
    data=await state.get_data()
    r=await session.execute(select(Vehicle).where(Vehicle.organization_id==db_user.organization_id,Vehicle.plate==data["plate"]))
    if r.scalar_one_or_none(): await msg.answer("⚠️ Bu raqam allaqachon mavjud."); await state.clear(); return
    session.add(Vehicle(organization_id=db_user.organization_id,plate=data["plate"],model=data["model"],driver=msg.text.strip()))
    await session.commit(); await state.clear()
    await msg.answer(f"✅ <b>{data['plate']}</b> bazaga qo'shildi.",parse_mode="HTML")

# ── Tarif sozlamalari ──

@router.callback_query(F.data=="adm:plans")
async def adm_plans(cb: CallbackQuery, session, db_user):
    if not _adm(db_user): await cb.answer(); return
    await svc.ensure_default_plans(session,db_user.organization_id); await session.commit()
    cfgs=await svc.get_all_cfgs(session,db_user.organization_id)
    rows=[[IB(text=f"{'📋' if c.plan.value=='basic' else '📊' if c.plan.value=='standard' else '🏆'} {c.name} — {c.price:,.0f} | {'∞' if c.unlimited else c.doc_limit}",callback_data=f"plan_edit:{c.plan.value}")] for c in cfgs]
    rows.append([IB(text="🔙 Admin panel",callback_data="adm:back")])
    await cb.message.edit_text("⚙️ <b>Tarif sozlamalari</b>",reply_markup=IM(inline_keyboard=rows),parse_mode="HTML"); await cb.answer()

@router.callback_query(F.data.startswith("plan_edit:"))
async def plan_edit_show(cb: CallbackQuery, session, db_user):
    if not _adm(db_user): await cb.answer(); return
    plan=SubPlan(cb.data.split(":",1)[1]); cfg=await svc.get_plan_cfg(session,db_user.organization_id,plan)
    if not cfg: await cb.answer("Topilmadi."); return
    info=(f"⚙️ <b>{cfg.name}</b>\n💰 {cfg.price:,.0f} {cfg.currency}\n"
          f"🔢 Limit: {'∞' if cfg.unlimited else cfg.doc_limit}\n"
          f"Excel:{'✅' if cfg.allow_excel else '❌'} Word:{'✅' if cfg.allow_word else '❌'} PDF:{'✅' if cfg.allow_pdf else '❌'}\n"
          f"OCR:{'✅' if cfg.allow_ocr else '❌'} Hisobot:{'✅' if cfg.allow_report else '❌'}\n"
          f"AI-Hisob:{'✅' if cfg.allow_ai_calc else '❌'} AI-Qidiruv:{'✅' if cfg.allow_ai_search else '❌'}")
    await cb.message.edit_text(info,reply_markup=plan_edit_kb(plan),parse_mode="HTML"); await cb.answer()

@router.callback_query(F.data.startswith("pe:"))
async def plan_field(cb: CallbackQuery, state: FSMContext, session, db_user):
    parts=cb.data.split(":"); field=parts[1]; plan_val=parts[2]
    plan=SubPlan(plan_val); cfg=await svc.get_plan_cfg(session,db_user.organization_id,plan)
    if field=="formats":
        await cb.message.edit_text(f"📊 <b>{cfg.name}</b> — Formatlar:",reply_markup=formats_kb(cfg),parse_mode="HTML")
        await state.update_data(editing_plan=plan_val); await cb.answer(); return
    if field=="funcs":
        await cb.message.edit_text(f"🛠 <b>{cfg.name}</b> — Funksiyalar:",reply_markup=funcs_kb(cfg),parse_mode="HTML")
        await state.update_data(editing_plan=plan_val); await cb.answer(); return
    if field=="ai":
        await cb.message.edit_text(f"🤖 <b>{cfg.name}</b> — Gemini AI:\nON=yoqilgan | OFF=o'chirilgan",reply_markup=ai_kb(cfg),parse_mode="HTML")
        await state.update_data(editing_plan=plan_val); await cb.answer(); return
    if field=="unlimited":
        cfg.unlimited=not cfg.unlimited; await session.commit()
        await cb.answer(f"{'♾ Cheksiz yoqildi' if cfg.unlimited else '🔢 Limit yoqildi'}"); await plan_edit_show(cb,session,db_user); return
    prompts={"name":"Yangi tarif nomi:","price":"Yangi narx (so'mda):","limit":"Yangi limit (nakladnoy soni):"}
    await state.set_state(AdminPlan.editing); await state.update_data(editing_plan=plan_val,editing_field=field)
    await cb.message.edit_text(prompts.get(field,"Qiymat:")); await cb.answer()

@router.message(AdminPlan.editing)
async def plan_field_save(msg: Message, state: FSMContext, session, db_user):
    data=await state.get_data(); plan=SubPlan(data["editing_plan"])
    field=data["editing_field"]; cfg=await svc.get_plan_cfg(session,db_user.organization_id,plan)
    val=msg.text.strip()
    if field=="name": cfg.name=val
    elif field=="price":
        try: cfg.price=float(val.replace(" ","").replace(",","."))
        except: await msg.answer("❌ Noto'g'ri son."); return
    elif field=="limit":
        try: cfg.doc_limit=int(val)
        except: await msg.answer("❌ Noto'g'ri son."); return
    await svc.audit_log(session,db_user.id,db_user.organization_id,"plan_edit",f"{plan.value}.{field}={val}")
    await session.commit(); await state.clear(); await msg.answer(f"✅ {plan.value} yangilandi.")

@router.callback_query(F.data.startswith("fmt_tog:"))
async def fmt_toggle(cb: CallbackQuery, state: FSMContext, session, db_user):
    action=cb.data.split(":",1)[1]; data=await state.get_data()
    if not data.get("editing_plan"): await cb.answer(); return
    plan=SubPlan(data["editing_plan"]); cfg=await svc.get_plan_cfg(session,db_user.organization_id,plan)
    if action=="excel": cfg.allow_excel=not cfg.allow_excel
    elif action=="word": cfg.allow_word=not cfg.allow_word
    elif action=="pdf": cfg.allow_pdf=not cfg.allow_pdf
    elif action=="save":
        await session.commit(); await state.clear()
        await cb.message.edit_text("✅ Formatlar saqlandi.",reply_markup=back_kb()); await cb.answer(); return
    await session.commit(); await cb.message.edit_reply_markup(reply_markup=formats_kb(cfg)); await cb.answer()

@router.callback_query(F.data.startswith("fn_tog:"))
async def fn_toggle(cb: CallbackQuery, state: FSMContext, session, db_user):
    action=cb.data.split(":",1)[1]; data=await state.get_data()
    if not data.get("editing_plan"): await cb.answer(); return
    plan=SubPlan(data["editing_plan"]); cfg=await svc.get_plan_cfg(session,db_user.organization_id,plan)
    if action=="ocr": cfg.allow_ocr=not cfg.allow_ocr
    elif action=="report": cfg.allow_report=not cfg.allow_report
    elif action=="transport": cfg.allow_transport=not cfg.allow_transport
    elif action=="calc": cfg.allow_calc=not cfg.allow_calc
    elif action=="templates": cfg.allow_templates=cfg.allow_templates%10+1
    elif action=="save":
        await session.commit(); await state.clear()
        await cb.message.edit_text("✅ Funksiyalar saqlandi.",reply_markup=back_kb()); await cb.answer(); return
    await session.commit(); await cb.message.edit_reply_markup(reply_markup=funcs_kb(cfg)); await cb.answer()

@router.callback_query(F.data.startswith("ai_tog:"))
async def ai_toggle(cb: CallbackQuery, state: FSMContext, session, db_user):
    action=cb.data.split(":",1)[1]; data=await state.get_data()
    if not data.get("editing_plan"): await cb.answer(); return
    plan=SubPlan(data["editing_plan"]); cfg=await svc.get_plan_cfg(session,db_user.organization_id,plan)
    if action=="ai_calc": cfg.allow_ai_calc=not cfg.allow_ai_calc
    elif action=="ai_search": cfg.allow_ai_search=not cfg.allow_ai_search
    elif action=="ai_report": cfg.allow_ai_report=not cfg.allow_ai_report
    elif action=="ai_anomaly": cfg.allow_ai_anomaly=not cfg.allow_ai_anomaly
    elif action=="ai_briefing": cfg.allow_ai_briefing=not cfg.allow_ai_briefing
    elif action=="ai_voice": cfg.allow_ai_voice=not cfg.allow_ai_voice
    elif action=="ai_chat": cfg.allow_ai_chat=not cfg.allow_ai_chat
    elif action=="save":
        await session.commit(); await state.clear()
        await cb.message.edit_text("✅ AI funksiyalar saqlandi.",reply_markup=back_kb()); await cb.answer(); return
    await session.commit(); await cb.message.edit_reply_markup(reply_markup=ai_kb(cfg)); await cb.answer()

# ── Obuna ──

@router.callback_query(F.data=="adm:sub")
async def adm_sub(cb: CallbackQuery, state: FSMContext, db_user):
    if not _adm(db_user): await cb.answer(); return
    await state.set_state(AdminSub.phone)
    await cb.message.edit_text("💳 <b>Obuna boshqaruvi</b>\n\nXodim telefon raqami:",parse_mode="HTML"); await cb.answer()

@router.message(AdminSub.phone)
async def sub_phone(msg: Message, state: FSMContext, session, db_user):
    r=await session.execute(select(User).where(User.organization_id==db_user.organization_id,User.phone==msg.text.strip()))
    u=r.scalar_one_or_none()
    if not u: await msg.answer("Xodim topilmadi."); return
    await state.update_data(target_name=u.full_name)
    cfgs=await svc.get_all_cfgs(session,db_user.organization_id)
    await state.set_state(AdminSub.choose_plan)
    await msg.answer(f"👤 <b>{u.full_name}</b>\nTarif tanlang:",reply_markup=plans_kb(cfgs),parse_mode="HTML")

@router.callback_query(AdminSub.choose_plan, F.data.startswith("plan:"))
async def sub_set(cb: CallbackQuery, state: FSMContext, session, db_user):
    plan=SubPlan(cb.data.split(":",1)[1]); data=await state.get_data()
    sub=await svc.get_sub(session,db_user.organization_id)
    if sub: sub.plan=plan; sub.status=SubStatus.ACTIVE; sub.docs_used=0; sub.updated_by=db_user.full_name
    else: session.add(Subscription(organization_id=db_user.organization_id,plan=plan,status=SubStatus.ACTIVE,updated_by=db_user.full_name))
    await svc.audit_log(session,db_user.id,db_user.organization_id,"sub_update",f"{data['target_name']}→{plan.value}")
    await session.commit(); await state.clear()
    await cb.message.edit_text(f"✅ <b>{data['target_name']}</b> → <b>{plan.value}</b>",parse_mode="HTML"); await cb.answer()

# ── Hisobot ──

@router.callback_query(F.data=="adm:report")
@router.message(F.text=="📊 Hisobot")
async def adm_report(event, session, db_user):
    msg_obj=event.message if isinstance(event,CallbackQuery) else event
    if db_user.role.value not in("admin","super_admin","manager"):
        await msg_obj.answer("🚫 Faqat rahbar/administrator uchun."); return
    now=dt.datetime.now(); ms=now.replace(day=1,hour=0,minute=0,second=0,microsecond=0)
    r=await session.execute(select(func.count()).select_from(Nakladnaya).where(Nakladnaya.organization_id==db_user.organization_id,Nakladnaya.created_at>=ms))
    total=r.scalar_one()
    r2=await session.execute(select(Nakladnaya.creator_id,func.count()).where(
        Nakladnaya.organization_id==db_user.organization_id,Nakladnaya.created_at>=ms).group_by(Nakladnaya.creator_id))
    by_user=r2.all(); sub=await svc.get_sub(session,db_user.organization_id)
    cfg=await svc.get_plan_cfg(session,db_user.organization_id,sub.plan) if sub else None
    limit="∞" if(cfg and cfg.unlimited) else(cfg.doc_limit if cfg else "—")
    lines=[f"📊 <b>{now.strftime('%B %Y')}</b>\nJami: <b>{total} ta</b> | Limit: <b>{limit}</b>\n"]
    for uid,cnt in sorted(by_user,key=lambda x:x[1],reverse=True):
        u=await session.get(User,uid); lines.append(f"  • {u.full_name if u else uid}: {cnt} ta")
    text="\n".join(lines)
    from database import settings as _s
    ai_btn=[[IB(text="🤖 AI tahlil",callback_data="report:ai")]] if(cfg and cfg.allow_ai_report and _s.GEMINI_API_KEY) else []
    kb=IM(inline_keyboard=ai_btn+back_kb().inline_keyboard)
    if isinstance(event,CallbackQuery): await msg_obj.edit_text(text,parse_mode="HTML",reply_markup=kb); await event.answer()
    else: await msg_obj.answer(text,parse_mode="HTML",reply_markup=kb)

@router.callback_query(F.data=="report:ai")
async def report_ai(cb: CallbackQuery, session, db_user):
    wait=await cb.message.answer("🤖 AI tahlil tayyorlanmoqda...")
    try:
        now=dt.datetime.now(); ms=now.replace(day=1,hour=0,minute=0,second=0,microsecond=0)
        r=await session.execute(select(func.count()).select_from(Nakladnaya).where(Nakladnaya.organization_id==db_user.organization_id,Nakladnaya.created_at>=ms))
        r2=await session.execute(select(Nakladnaya.creator_id,func.count()).where(Nakladnaya.organization_id==db_user.organization_id,Nakladnaya.created_at>=ms).group_by(Nakladnaya.creator_id))
        by_user=[]; 
        for uid,cnt in r2.all():
            u=await session.get(User,uid); by_user.append({"xodim":u.full_name if u else str(uid),"count":cnt})
        ai_text=await svc.ai_report({"oy":now.strftime("%B %Y"),"jami":r.scalar_one(),"xodimlar":by_user})
        await wait.delete(); await cb.message.answer(f"🤖 <b>AI tahlil:</b>\n\n{ai_text}",parse_mode="HTML",reply_markup=back_kb())
    except Exception as e: await wait.delete(); await cb.message.answer(f"❌ AI xato: {e}")
    await cb.answer()

# ── Audit ──

@router.callback_query(F.data=="adm:audit")
async def adm_audit(cb: CallbackQuery, session, db_user):
    if not _adm(db_user): await cb.answer(); return
    r=await session.execute(select(AuditLog).where(AuditLog.org_id==db_user.organization_id).order_by(AuditLog.created_at.desc()).limit(20))
    logs=r.scalars().all()
    if not logs: await cb.message.edit_text("Jurnal bo'sh.",reply_markup=back_kb()); await cb.answer(); return
    lines=["📒 <b>Audit jurnali (20 ta):</b>\n"]
    for l in logs:
        d=l.created_at.strftime("%d.%m %H:%M") if l.created_at else ""
        lines.append(f"{'⚠️' if l.suspicious else '▪'} <code>{d}</code> | {l.action} | {l.detail[:40]}")
    await cb.message.edit_text("\n".join(lines),parse_mode="HTML",reply_markup=back_kb()); await cb.answer()

@router.callback_query(F.data=="adm:suspicious")
async def adm_suspicious(cb: CallbackQuery, session, db_user):
    if not _adm(db_user): await cb.answer(); return
    r=await session.execute(select(AuditLog).where(AuditLog.org_id==db_user.organization_id,AuditLog.suspicious==True).order_by(AuditLog.created_at.desc()).limit(20))
    logs=r.scalars().all()
    if not logs: await cb.message.edit_text("⚠️ Shubhali harakatlar yo'q.",reply_markup=back_kb()); await cb.answer(); return
    lines=["⚠️ <b>Shubhali harakatlar:</b>\n"]
    for l in logs:
        u=await session.get(User,l.user_id) if l.user_id else None
        d=l.created_at.strftime("%d.%m %H:%M") if l.created_at else ""
        lines.append(f"⚠️ <code>{d}</code> | {u.full_name if u else '?'}\n   {l.detail}\n")
    await cb.message.edit_text("\n".join(lines),parse_mode="HTML",reply_markup=back_kb()); await cb.answer()

@router.callback_query(F.data=="adm:org")
async def adm_org(cb: CallbackQuery, state: FSMContext, session, db_user):
    if not _adm(db_user): await cb.answer(); return
    org=await session.get(Organization,db_user.organization_id)
    await state.set_state(AdminObj.text)
    await cb.message.edit_text(f"🏗 Standart obyekt:\n{org.object_text if org else '—'}\n\nYangi matn yozing ('.' — o'zgartirmaslik):",parse_mode="HTML"); await cb.answer()

@router.message(AdminObj.text)
async def org_obj_save(msg: Message, state: FSMContext, session, db_user):
    if msg.text.strip()!=".":
        org=await session.get(Organization,db_user.organization_id)
        if org: org.object_text=msg.text.strip()
        await session.commit(); await msg.answer("✅ Saqlandi.")
    await state.clear()

# ══════════════════════════════════════════════════════════════
# SUPER ADMIN
# ══════════════════════════════════════════════════════════════

@router.message(Command("neworg"))
async def new_org(msg: Message, session):
    from database import settings as _s
    if msg.from_user.id!=_s.SUPER_ADMIN_ID: return
    parts=msg.text.split(maxsplit=1)
    if len(parts)!=2: await msg.answer('/neworg "Nomi"'); return
    org=Organization(name=parts[1].strip()); session.add(org); await session.flush()
    session.add(Subscription(organization_id=org.id,plan=SubPlan.BASIC,status=SubStatus.TRIAL))
    await svc.ensure_default_plans(session,org.id); await session.commit()
    await msg.answer(f"✅ ID: <b>{org.id}</b> | <b>{org.name}</b>",parse_mode="HTML")

@router.message(Command("newadmin"))
async def new_admin(msg: Message, session):
    from database import settings as _s
    if msg.from_user.id!=_s.SUPER_ADMIN_ID: return
    parts=msg.text.split(maxsplit=3)
    if len(parts)!=4: await msg.answer("/newadmin <org_id> <tel> <F.I.Sh>"); return
    _,org_id,phone,name=parts; org=await session.get(Organization,int(org_id))
    if not org: await msg.answer("Tashkilot topilmadi."); return
    r=await session.execute(select(AllowedPhone).where(AllowedPhone.phone_number==phone))
    if r.scalar_one_or_none(): await msg.answer("Bu raqam mavjud."); return
    session.add(AllowedPhone(organization_id=org.id,phone_number=phone,full_name=name,role=UserRole.ADMIN))
    await session.commit()
    await msg.answer(f"✅ <b>{name}</b> ({phone}) → <b>{org.name}</b>",parse_mode="HTML")

@router.message(Command("orglist"))
async def org_list(msg: Message, session):
    from database import settings as _s
    if msg.from_user.id!=_s.SUPER_ADMIN_ID: return
    r=await session.execute(select(Organization)); orgs=r.scalars().all()
    if not orgs: await msg.answer("Tashkilotlar yo'q."); return
    await msg.answer("\n".join(f"#{o.id} — {o.name}" for o in orgs))
