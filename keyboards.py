from models import UserRole, SubPlan
"""Barcha FSM holatlari va tugmalar."""
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    InlineKeyboardButton as IB, InlineKeyboardMarkup as IM,
    KeyboardButton as KB, ReplyKeyboardMarkup as RM, ReplyKeyboardRemove
)

# ══ STATES ════════════════════════════════════════════════════
class Reg(StatesGroup):
    phone=State(); full_name=State(); password=State(); confirm_pw=State()

class Nak(StatesGroup):
    doc_type=State(); obj=State(); sender=State(); receiver=State()
    vehicle=State(); veh_model=State(); driver=State(); destination=State()
    item=State(); item_search=State(); item_unit=State(); item_qty=State()
    more=State(); template=State(); fmt=State(); confirm=State()

class OCR(StatesGroup):
    waiting_photo=State(); confirm=State()

class Calc(StatesGroup):
    expr=State()

class PwChange(StatesGroup):
    old_pw=State(); new_pw=State(); confirm=State()

class AdminUser(StatesGroup):
    phone=State(); name=State(); position=State(); role=State()

class AdminVeh(StatesGroup):
    plate=State(); model=State(); driver=State()

class AdminMat(StatesGroup):
    bulk=State(); search=State()

class AdminPlan(StatesGroup):
    choose_plan=State(); editing=State()

class AdminSub(StatesGroup):
    phone=State(); choose_plan=State()

class AdminObj(StatesGroup):
    text=State()

# ══ KEYBOARDS ════════════════════════════════════════════════

TEMPLATES_NAMES={1:"Klassik",2:"Ixcham",3:"Korporativ",4:"Batafsil",5:"Sodda",
                 6:"Mahsulot",7:"Transport",8:"Ikki tilli",9:"A5",10:"Qurilish"}

def rm(): return ReplyKeyboardRemove()
def contact_kb(): return RM(keyboard=[[KB(text="📱 Telefon raqamni yuborish",request_contact=True)]],resize_keyboard=True,one_time_keyboard=True)

def main_menu(role,has_ocr=False):
    rows=[[KB(text="🆕 Yangi nakladnoy"),KB(text="🧮 Hisoblash")],
          [KB(text="📜 Tarixim"),KB(text="⚙️ Sozlamalar")]]
    if has_ocr: rows.insert(1,[KB(text="📸 Rasm → Excel")])
    if role.value in("admin","super_admin"): rows.append([KB(text="🛠 Admin panel")])
    if role.value=="manager": rows.append([KB(text="📊 Hisobot")])
    return RM(keyboard=rows,resize_keyboard=True)

def doc_type_kb(): return IM(inline_keyboard=[
    [IB(text="📤 Chiqim (skladdan)",callback_data="dt:chiqim")],
    [IB(text="↩️ Qaytarish (obyektdan)",callback_data="dt:qaytarish")]])

def skip_kb(cb="skip"): return IM(inline_keyboard=[
    [IB(text="⏭ O'tkazish",callback_data=cb)],
    [IB(text="✏️ Bo'sh (___)",callback_data=f"{cb}_blank")]])

def units_kb(): return IM(inline_keyboard=[
    [IB(text=u,callback_data=f"unit:{u}") for u in ["шт","кг","литр","м"]],
    [IB(text=u,callback_data=f"unit:{u}") for u in ["м²","тонна","к-т","п.м"]]])

def search_kb(mats): return IM(inline_keyboard=[
    *[[IB(text=f"📦 {m.code} — {m.name[:38]}",callback_data=f"mat:{m.id}")] for m in mats[:8]],
    [IB(text="✏️ Qo'lda kiritish",callback_data="mat:manual")]])

def more_kb(n): return IM(inline_keyboard=[
    [IB(text=f"➕ Yana qo'shish ({n} ta)",callback_data="more:yes")],
    [IB(text="✅ Tugatish → Davom",callback_data="more:no")]])

def template_kb(max_t=10): return IM(inline_keyboard=[
    [IB(text=f"{'📋' if i<=2 else '📄'} {TEMPLATES_NAMES[i]}",callback_data=f"tpl:{i}")]
    for i in range(1,max_t+1)])

def format_kb(cfg): return IM(inline_keyboard=[
    *([[IB(text="📊 Excel",callback_data="fmt:excel")]] if not cfg or cfg.allow_excel else []),
    *([[IB(text="📄 Word",callback_data="fmt:word")]] if cfg and cfg.allow_word else []),
    *([[IB(text="🧾 PDF",callback_data="fmt:pdf")]] if cfg and cfg.allow_pdf else [])])

def confirm_kb(): return IM(inline_keyboard=[
    [IB(text="✅ Tasdiqlash",callback_data="confirm:yes")],
    [IB(text="✏️ Tahrirlash",callback_data="confirm:edit")],
    [IB(text="❌ Bekor",callback_data="confirm:no")]])

def plans_kb(cfgs): return IM(inline_keyboard=[
    [IB(text=f"{'📋' if c.plan.value=='basic' else '📊' if c.plan.value=='standard' else '🏆'} {c.name} — {c.price:,.0f} {c.currency}",
        callback_data=f"plan:{c.plan.value}")] for c in cfgs])

def nak_view_kb(nid,cfg): return IM(inline_keyboard=[
    [IB(text="🖼 Ko'rinish",callback_data=f"view:preview:{nid}")],
    [*([IB(text="📊 Excel",callback_data=f"view:excel:{nid}")] if not cfg or cfg.allow_excel else []),
     *([IB(text="📄 Word",callback_data=f"view:word:{nid}")] if cfg and cfg.allow_word else []),
     *([IB(text="🧾 PDF",callback_data=f"view:pdf:{nid}")] if cfg and cfg.allow_pdf else [])],
    [IB(text="🗑 O'chirish",callback_data=f"view:del:{nid}")]])

def calc_mode_kb(has_ai): return IM(inline_keyboard=[
    [IB(text="🔢 Oddiy hisoblash",callback_data="calc:simple")],
    *([[IB(text="🤖 AI hisoblash (Gemini)",callback_data="calc:ai")]] if has_ai else []),
    [IB(text="🔙 Orqaga",callback_data="calc:back")]])

def admin_kb(): return IM(inline_keyboard=[
    [IB(text="👥 Foydalanuvchilar",   callback_data="adm:users")],
    [IB(text="📦 Mahsulot bazasi",    callback_data="adm:mat")],
    [IB(text="🚛 Transport bazasi",   callback_data="adm:veh")],
    [IB(text="💳 Obuna boshqaruvi",   callback_data="adm:sub")],
    [IB(text="⚙️ Tarif sozlamalari",  callback_data="adm:plans")],
    [IB(text="📊 Hisobot",            callback_data="adm:report")],
    [IB(text="📒 Audit jurnali",       callback_data="adm:audit")],
    [IB(text="⚠️ Shubhali harakatlar",callback_data="adm:suspicious")],
    [IB(text="🏗 Tashkilot",           callback_data="adm:org")]])

def users_kb(): return IM(inline_keyboard=[
    [IB(text="➕ Yangi xodim",         callback_data="usr:add")],
    [IB(text="📋 Ro'yxat",             callback_data="usr:list")],
    [IB(text="🔴 Bloklash",             callback_data="usr:block_menu")],
    [IB(text="🟢 Blokdan chiqarish",    callback_data="usr:unblock_menu")],
    [IB(text="⏸ Tekshiruv rejimi",      callback_data="usr:freeze_menu")],
    [IB(text="📈 Statistika",           callback_data="usr:stats")],
    [IB(text="🏆 Reyting",              callback_data="usr:rating")]])

def mat_kb(): return IM(inline_keyboard=[
    [IB(text="➕ Ko'plab qo'shish", callback_data="mat:bulk")],
    [IB(text="🔍 Qidirish",         callback_data="mat:search")],
    [IB(text="🗑 O'chirish",         callback_data="mat:delete")],
    [IB(text="📊 Statistika",        callback_data="mat:stats")]])

def plan_edit_kb(plan): return IM(inline_keyboard=[
    [IB(text="✏️ Nomi",              callback_data=f"pe:name:{plan.value}")],
    [IB(text="💰 Narxi",             callback_data=f"pe:price:{plan.value}")],
    [IB(text="🔢 Limit",             callback_data=f"pe:limit:{plan.value}")],
    [IB(text="📊 Formatlar",         callback_data=f"pe:formats:{plan.value}")],
    [IB(text="🛠 Funksiyalar",        callback_data=f"pe:funcs:{plan.value}")],
    [IB(text="🤖 Gemini AI",          callback_data=f"pe:ai:{plan.value}")],
    [IB(text="♾ Cheksiz",             callback_data=f"pe:unlimited:{plan.value}")]])

def formats_kb(cfg): return IM(inline_keyboard=[
    [IB(text=f"{'✅' if cfg.allow_excel else '❌'} Excel", callback_data="fmt_tog:excel")],
    [IB(text=f"{'✅' if cfg.allow_word  else '❌'} Word",  callback_data="fmt_tog:word")],
    [IB(text=f"{'✅' if cfg.allow_pdf   else '❌'} PDF",   callback_data="fmt_tog:pdf")],
    [IB(text="✅ Saqlash",                                 callback_data="fmt_tog:save")]])

def funcs_kb(cfg): return IM(inline_keyboard=[
    [IB(text=f"{'✅' if cfg.allow_ocr       else '❌'} 📸 OCR",       callback_data="fn_tog:ocr")],
    [IB(text=f"{'✅' if cfg.allow_report    else '❌'} 📊 Hisobot",   callback_data="fn_tog:report")],
    [IB(text=f"{'✅' if cfg.allow_transport else '❌'} 🚛 Transport", callback_data="fn_tog:transport")],
    [IB(text=f"{'✅' if cfg.allow_calc      else '❌'} 🧮 Hisoblash", callback_data="fn_tog:calc")],
    [IB(text=f"📋 Shablonlar: {cfg.allow_templates} ta",              callback_data="fn_tog:templates")],
    [IB(text="✅ Saqlash",                                             callback_data="fn_tog:save")]])

def ai_kb(cfg): return IM(inline_keyboard=[
    [IB(text=f"{'ON' if cfg.allow_ai_calc      else 'OFF'} 🧮 AI Hisoblash",  callback_data="ai_tog:ai_calc")],
    [IB(text=f"{'ON' if cfg.allow_ai_search    else 'OFF'} 🔍 AI Qidiruv",    callback_data="ai_tog:ai_search")],
    [IB(text=f"{'ON' if cfg.allow_ai_report    else 'OFF'} 📊 AI Hisobot",    callback_data="ai_tog:ai_report")],
    [IB(text=f"{'ON' if cfg.allow_ai_anomaly   else 'OFF'} ⚠️ Anomaliya",    callback_data="ai_tog:ai_anomaly")],
    [IB(text=f"{'ON' if cfg.allow_ai_briefing  else 'OFF'} ☀️ Brifing",      callback_data="ai_tog:ai_briefing")],
    [IB(text=f"{'ON' if cfg.allow_ai_voice     else 'OFF'} 🎤 Ovoz",         callback_data="ai_tog:ai_voice")],
    [IB(text=f"{'ON' if cfg.allow_ai_chat      else 'OFF'} 💬 Suhbat",       callback_data="ai_tog:ai_chat")],
    [IB(text="✅ Saqlash",                                                     callback_data="ai_tog:save")]])

def back_kb(): return IM(inline_keyboard=[[IB(text="🔙 Admin panel",callback_data="adm:back")]])
def pw_kb(): return IM(inline_keyboard=[[IB(text="🔑 Parolni o'zgartirish",callback_data="pw:change")]])
def ocr_confirm_kb(): return IM(inline_keyboard=[
    [IB(text="✅ To'g'ri, Excel yaratish",callback_data="ocr:confirm")],
    [IB(text="❌ Bekor",callback_data="ocr:cancel")]])
