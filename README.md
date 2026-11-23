# المنظومة القانونية السعودية للذكاء الاصطناعي 🇸🇦
# Saudi Legal AI Framework — OpenClaw Edition

[![Version](https://img.shields.io/badge/version-0.4.0--pre-blue.svg)](https://github.com/SMSMy/saudi-legal-ai)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![OpenClaw](https://img.shields.io/badge/OpenClaw-ready-green.svg)](https://openclaw.ai)

> ⚠️ للبحث الأولي فقط — ليس استشارة قانونية. يجب مراجعة مختص قانوني مرخص في المملكة العربية السعودية.
> For preliminary research only — not legal advice. Must be reviewed by a licensed Saudi legal professional.

> **ترقيم الإصدار / Versioning:** رقم semver في `pyproject.toml` هو المرجع الرسمي الوحيد
> (حالياً `0.4.0` — قبل الإصدار الأول). أرقام `v0.4.x` في رسائل الـcommits
> علامات تغيير داخلية، **ليست إصدارات**. عند أول إصدار رسمي يُرفع semver
> ويُولَّد `releases/<version>-evidence.json` عبر `generate_release_evidence.py`.

---

## 🦞 مبني لـ OpenClaw | Built for OpenClaw

هذه النسخة **مُكيّفة خصيصاً لـ [OpenClaw](https://openclaw.ai)** — مساعد ذكي متعدد القنوات والنماذج.

> This edition is **specifically adapted for OpenClaw** — a multi-channel, multi-model AI assistant.

**الفرق عن النسخة الأصلية:**
- ✅ سيرفر **استرجاع خالص** — لا يحتاج أي مفتاح API (المساعد هو اللي يحلل بالنموذج النشط)
- ✅ تكامل كامل مع OpenClaw — أي نموذج (DeepSeek, GLM, Mimo, ...) يشتغل مباشرة
- ✅ لا Docker، لا Anthropic، لا مفاتيح خارجية

**What's different from the original:**
- ✅ Pure **retrieval server** — no API keys needed (the agent analyzes with its active model)
- ✅ Full OpenClaw integration — any model works out of the box
- ✅ No Docker, no Anthropic, no external keys

---

## 📦 تركيب سريع | Quick Install

```bash
# 1. Clone + venv
git clone https://github.com/SMSMy/saudi-legal-ai.git
cd saudi-legal-ai
python3 -m venv .venv
.venv/bin/pip install -e .

# 2. Register in OpenClaw
openclaw mcp set saudi-legal \
  '{"command":"'$(pwd)'/.venv/bin/saudi-legal-mcp","args":[]}'

# 3. Reload
openclaw mcp reload
```

**Done!** Legal tools ready — standard Python package, no env-var hacks needed. 🔓

> **تلميح:** الحزمة تثبّت `mcp<2.0.0` تلقائياً (مُقيَّدة في pyproject.toml).
> لو ظهر خطأ `ModuleNotFoundError: No module named 'mcp.server.fastmcp'`
> فبيئتك فيها mcp 2.0.0 — أزله ثم أعد التثبيت: `pip uninstall mcp && pip install -e .`

---

## 🛠️ الأدوات | Tools

| الأداة | الوصف |
|--------|---------|
| `get_legal_skill` | استرجاع/تحميل المهارات القانونية المجالية بالكامل (أو metadata / section فقط) |
| `get_regulation_source` | قراءة المصادر النظامية المحددة (metadata افتراضياً؛ include_content لقراءة النص). **روابط موثقة**: `citations[]` تحمل `link_type` يميّز رابط الجهة العامة عن رابط المادة المباشر — والـlabel يوضح الفرق نصياً |
| `get_legal_context` | تجميع سياق قانوني موحّد (مهارة + مصدر + حالة في استدعاء واحد) |
| `search_contract_risks` | بحث في مخاطر العقود مع policy enforcement (evidence إلزامي) |
| `list_legal_domains` | قائمة كل المجالات والمصادر المتاحة مع حالة التحقق |
| `get_source_status` | حالة المصدر: verification_status + صياغة عربية مفهومة (لا مصطلحات داخلية) + تحذير منتهي الصلاحية |
| `report_source_issue` | تسجيل مشكلة في مصدر (يتطلب ENABLE_LOCAL_REPORTS=true) |
| `search_legal_provision` | بحث نصي في نصوص الأنظمة (تطبيع عربي: أل التعريف، همزات، تشكيل + ترادف موثق). **بوابة ثقة 0.7**: الأقسام الأضعف تُستبعد برمجياً. كل قسم يحمل `citations` من نطاقه هو |
| `get_legal_brief` | مذكرة موحّدة من مهارة + نصوص + مخاطر تختتم بقسم "المصادر والروابط". **بوابات إلزامية**: `insufficient_evidence` عند نقص الدليل أو هيمنة `[يحتاج تحقق]` |

**سياسة الأدلة (evidence policy):** لا ادعاء بلا citation داخل المستودع. أي نتيجة يجب أن تحمل `evidence[]` أو `insufficient_evidence: true`. عند اقتطاع المحتوى الطويل يُعاد `sections_index` (فهرس العناوين) ليكتشف الوكيل الأقسام البعيدة بدل تخمينها.

---

## 🚧 بوابة الإصدار | Release Gate

كل تعديل على المصادر النظامية يمر عبر بوابة برمجية — الحماية **بنيوية** لا تعتمد على انضباط المساهم:

```bash
python scripts/verify_release.py
```

| البوابة | ماذا تمنع |
|---------|-----------|
| `generate_manifests.py --check` | تعديل مصدر بدون تحديث الـmanifest (sha256 غير متطابق → exit 1 برسالة إرشادية دقيقة) |
| `validate_manifests.py` | manifests ناقصة/يتيمة/ذات حقول قانونية بلا مراجعة بشرية |
| `pytest tests/ -q` | 109 اختباراً — منها حراسة تسجيل الأدوات، تغطية كل مصدر بأسئلة eval، وتفاعل بوابات الثقة |
| مقارنة الـeval بالـbaseline المعياري | انحدار `citation_precision`/`source_recall` بأكثر من 1% → تحذير صريح |

**Evidence bundle:** `generate_release_evidence.py` ينتج `releases/<version>-evidence.json` —
مصدر الحقيقة المعلن لأي إصدار، وكل رقم فيه مسحوب من تشغيل فعلي
(git commit، عدّ manifests، pytest حقيقي، eval منفذة، بوابات مُثبتة سلوكياً).

---

## 📚 المحتوى | Content

| المجلد | المحتوى |
|--------|---------|
| `skills/` | 9 مهارات قانونية: العقود، نظام العمل، حماية البيانات، النزاعات، الشركات، العقارات، التجارة الإلكترونية، الرياضة، ZATCA |
| `sources/` | 20 مصدر نظامي (source_documents_count=20، reference_collections_count=2، verified_sources_count=0) |
| `sources/manifests/` | 20 manifest JSON لكل مصدر (sha256، verification_status، مواعيد المراجعة الدورية) |
| `datasets/` | مجموعة مخاطر تعاقدية + جدول مصادر + تعريفات المجال |
| `examples/` | 14 مثال تفاعلي مع كل الأدوات |
| `prompts/` | نصوص التوجيه (الإجابة الآمنة، الصياغة المقيدة، الكشف عن المخاطر) |
| `scripts/` | generate_manifests.py (مع --check) · validate_manifests.py · verify_release.py · generate_release_evidence.py · propose_verification.py · verify_all_manifests.py · audit_substring_vs_wordboundary.py |
| `tests/` | 109 اختباراً آلياً (بدون API خارجي) — تشمل حراسة تسجيل الأدوات، بوابات الثقة، release gate، و`tests/adversarial/` (حقن الأوامر) |
| `evals/` | corpus 65 سؤالاً عبر الـ20 مصدراً + eval_runner.py — آخر أرقام: precision=97.2%، recall=90.3% |
| `releases/` | evidence bundles (`0.4.0-evidence.json`) — المصدر المعلن للحقائق لكل إصدار |
| `memory/` | دروس الجلسات الحرجة — ما تعلمه المشروع من اكتشافات الاستخدام الفعلي |

---

## 🔒 الأمان | Security

- ✅ **بدون أي مفتاح API** — السيرفر لا يتصل بأي خدمة خارجية
- ✅ **بيانات محلية** — كل الملفات نصية مقروءة محلياً
- ✅ **مصادر رسمية** — الأنظمة منشورة على boe.gov.sa و uqn.gov.sa
- ✅ **مُثبَت ضد حقن الأوامر** — `tests/adversarial/`: لا SDK نموذج ولا HTTP client في الحزمة (فحص بنيوي)، ونص تعليمات محقون في مصدر يُعاد كنص عادي مع بقاء الـdisclaimer الإلزامي (إثبات سلوكي)
- ⚠️ **ليس استشارة قانونية** — للمراجعة الأولية فقط

---

## 🧱 حدود الضمان | Guarantee Boundaries

**ما يضمنه السيرفر (ويُثبته بالاختبارات):**

- أدواته **لا تختلق** — أي نتيجة تحمل `evidence[]` أو `insufficient_evidence: true`
- الأقسام دون عتبة الثقة تُستبعد، والقوالب الفارغة (`[يحتاج تحقق]`) تُرفض بواباتها
- الروابط تُرجع بنوعها الصريح (`link_type`)، وغيابها يُعلَن عبر `citation_note` لا يُخفى

**ما لا يضمنه السيرفر — حد بنيوي صريح لا ثغرة قابلة للسد:**

هذا سيرفر **استرجاع خالص** — لا يحلل ولا يملك سلطة على كيفية **صياغة**
الوكيل المستهلك (OpenClaw/GPT/Claude...) لإجابته النهائية. الوكيل قد
يدمج معرفة عامة من ذاته بثقة الأدلة المسترجعة دون تمييز — **لا تستنتج
أن كل إجابة نهائية موثَّقة بالضرورة** لمجرد أن السيرفر يفرض
`enforce_evidence` داخلياً.

**قواعد الصياغة — قنوات الإيصال الفعلية (مُثبَت بفحص كود العميل):**

قواعد الصياغة الأربع (وسم المعرفة العامة، لا رقم بلا citation، نقل
`citation_note`، الامتناع أولى من التكميل) مضمَّنة في:

1. **docstrings الأدوات** — القناة المؤكدة: فحص كود OpenClaw المثبَّت
   أثبت أنه يمرر `tool.description` فقط للنموذج، ولا يقرأ حقل
   `instructions` من MCP handshake إطلاقاً. القواعد الآن في docstrings
   `get_regulation_source` و`search_legal_provision` و`get_legal_brief`
   (محروسة باختبار يفشل عند حذفها).
2. **حقول المخرجات** — `insufficient_evidence` و`citation_note`
   و`verification_status_explanation` و`disclaimer` يراها النموذج في
   كل استجابة JSON.
3. حقل `instructions` — يبقى لعملاء MCP آخرين قد يعرضونه، لكن
   **لا يُعتمد عليه** مع OpenClaw (درس v0.4.15: التوافق مع مواصفة
   البروتوكول لا يضمن استهلاك العميل الفعلي له).

**لا ضمان إنفاذ على أي من هذه القنوات** — الالتزام بها يبقى بيد
النموذج المستهلك، وأي system prompt يكتبه المستخدم يتفوق عليها
طبيعياً. النسخة الكاملة المرجعية:
[`prompts/answer-drafting-discipline.md`](saudi_legal_mcp/data/prompts/answer-drafting-discipline.md)

---

## 🤝 المساهمة | Contributing

> 🔴 **الأولوية القصوى — نبحث عن مراجعة قانونية بشرية:**
> محامٍ أو مستشار قانوني مرخّص في المملكة لمراجعة دقة المصادر النظامية
> (20 مصدراً كلها `field_tested` — أي مُجرَّبة تقنياً — بانتظار الترقية
> إلى `verified` عبر مراجعة مختص). **هذه أثمن مساهمة ممكنة الآن**، وهي
> الطريق الوحيد الذي يحوّل "يعمل تقنياً" إلى "صحيح قانونياً".
> معايير الترقية موثقة في [legal_response_policy.md](legal_response_policy.md).

المنظومة القانونية السعودية مشروع مفتوح المصدر. رحب بمساهماتك: إضافة أنظمة جديدة، تحسين المهارات، بيانات مخاطر، أمثلة تطبيقية.

راجع [CONTRIBUTING.md](CONTRIBUTING.md) للتفاصيل.

This is an open-source project. Contributions welcome: new regulations, improved skills, risk data, worked examples.

---

## 📄 الرخص | License

MIT License — للاستخدام الحر مع نسب المصدر والاحتفاظ بإخلاء المسؤولية القانوني.

MIT License — free to use with attribution and retention of legal disclaimer.

---

## 🔗 الشكر | Credits

- النسخة الأصلية: [Samix2026/saudi-legal-ai-framework](https://github.com/Samix2026/saudi-legal-ai-framework)
- هذا الـ fork: مُكيّف خصيصاً لـ OpenClaw بواسطة [SMSMy](https://github.com/SMSMy)
