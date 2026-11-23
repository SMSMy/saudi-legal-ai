# المنظومة القانونية السعودية للذكاء الاصطناعي 🇸🇦 — Saudi Legal AI MCP retrieval server

[![Version](https://img.shields.io/badge/version-0.5.0-blue.svg)](https://github.com/SMSMy/saudi-legal-ai/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![MCP](https://img.shields.io/badge/MCP-stdio-blue.svg)](https://modelcontextprotocol.io)

> ⚠️ للبحث الأولي فقط — ليس استشارة قانونية. يجب مراجعة مختص قانوني مرخص في المملكة العربية السعودية.
> For preliminary research only — not legal advice. Must be reviewed by a licensed Saudi legal professional.

> **ترقيم الإصدار / Versioning:** رقم semver في `pyproject.toml` هو المرجع الرسمي الوحيد
> (حاليًا `0.5.0`؛ `0.4.0` كان الإصدار الرسمي الأول ودليل أدلته محفوظ في `releases/`).
> أرقام `v0.4.x` في رسائل الـcommits علامات تغيير داخلية، **ليست إصدارات**.

---

## 🔌 سيرفر MCP مستقل | An independent MCP server

هذه نواة **استرجاع محلي** تعمل مع أي وكيل يتكلم MCP: OpenClaw وClaude Desktop
وCursor وCline وCodex وGemini CLI وغيرها. لا تحتاج مفتاح API ولا Docker ولا
اتصالاً خارجياً في مسار الطلب.

> A **local retrieval core** for any MCP-capable agent: OpenClaw, Claude Desktop,
> Cursor, Cline, Codex, Gemini CLI, and others. No API keys, no Docker, no
> network calls in the request path.

**ما يميزها:**
- ✅ **اقتباس رسمي** من `corpus/` مع رابط وتاريخ سحب، لا ملخص يُقدَّم كنص نظامي
- ✅ **إسناد صريح**: `portal` / `law_document_url` / `direct_article_url` — والملخص اليدوي `hand_written_summary`
- ✅ سيرفر استرجاع خالص — أي نموذج يعمل، والمفاتيح خارج النواة
- ✅ لا Docker، لا Anthropic، لا مفاتيح خارجية

**What it does:**
- ✅ **Official quotes** from `corpus/` with a link and fetch date — not a summary dressed as statute
- ✅ **Honest provenance**: `portal` / `law_document_url` / `direct_article_url`; hand-written text is `hand_written_summary`
- ✅ Pure retrieval — any model works; keys stay outside the core
- ✅ No Docker, no Anthropic, no external keys

---

## 📦 تركيب سريع | Quick Install

```bash
# 1. Clone + venv
git clone https://github.com/SMSMy/saudi-legal-ai.git
cd saudi-legal-ai
python3 -m venv .venv
.venv/bin/pip install -e .   # Linux/macOS
# Windows (PowerShell): .venv\Scripts\pip install -e .

# 2. Register in OpenClaw
openclaw mcp set saudi-legal \
  '{"command":"'$(pwd)'/.venv/bin/saudi-legal-mcp","args":[]}'
# Windows (PowerShell): '{"command":"'$(Get-Location)'\\.venv\\Scripts\\saudi-legal-mcp.exe","args":[]}'

# 3. Reload
openclaw mcp reload
```

**Done!** Legal tools ready — standard Python package, no env-var hacks needed. 🔓

## ✅ ما لا تحتاجه | What you DON'T need

- 🔑 **لا مفتاح API** — السيرفر استرجاع خالص؛ لا يستدعي أي نموذج لغوي ولا أي خدمة خارجية في مسار الطلب.
- 🐳 **لا Docker** — أمر `pip install -e .` يكفي، وأمر stdio واحد (`saudi-legal-mcp`) يُسجَّل في أي عميل MCP.
- 🌐 **لا اتصال خارجي في مسار الطلب** — كل القراءة من ملفات محلية. اللمسة الشبكية الوحيدة هي سكربتات السحب الصريحة (`scripts/ingest_laws.py` ونحوها) التي يشغّلها إنسان بيده من داخل المملكة، وليست جزءًا من مسار الإجابة.

> OpenClaw هنا **مثال على عميل MCP** فقط. نفس أمر stdio يعمل في Claude Desktop
> وCursor وCline وCodex وGemini CLI وأي عميل MCP آخر.
>
> OpenClaw is **one MCP client example**. The same stdio command works in
> Claude Desktop, Cursor, Cline, Codex, Gemini CLI, and any other MCP client.

> **تلميح:** الحزمة تثبّت `mcp<2.0.0` تلقائياً (مُقيَّدة في pyproject.toml).
> لو ظهر خطأ `ModuleNotFoundError: No module named 'mcp.server.fastmcp'`
> فبيئتك فيها mcp 2.0.0 — أزله ثم أعد التثبيت: `pip uninstall mcp && pip install -e .`

---

## 🛠️ الأدوات | Tools

| الأداة | الوصف |
|--------|---------|
| `get_legal_skill` | استرجاع/تحميل المهارات القانونية المجالية بالكامل (أو metadata / section فقط) |
| `get_regulation_source` | قراءة **الملخص المكتوب يدوياً** لمصدر نظامي (metadata افتراضياً؛ include_content للنص). كل نتيجة تحمل `text_origin: hand_written_summary` و`provenance_level`، ولا تُقدَّم كنص رسمي. **روابط موثقة**: `link_type` يميّز `portal` عن `law_document_url` عن `direct_article_url` |
| `get_legal_context` | تجميع سياق قانوني موحّد (مهارة + مصدر + حالة في استدعاء واحد) |
| `search_contract_risks` | بحث في مخاطر العقود مع policy enforcement (evidence إلزامي) |
| `list_legal_domains` | قائمة المجالات والمصادر مع **توزيع مستويات الإسناد** (وثيقة/بوابة/مُسحوب/مادة)، لا `verified_count` |
| `get_source_status` | حالة المصدر: verification_status + صياغة عربية مفهومة (لا مصطلحات داخلية) + تحذير منتهي الصلاحية |
| `report_source_issue` | تسجيل مشكلة في مصدر (يتطلب ENABLE_LOCAL_REPORTS=true) |
| `search_legal_provision` | **يبحث المخزن الحرفي أولاً**: يعيد `quotes[]` بـ`text_origin: official_verbatim` مع رابط وتاريخ سحب. إن لم يجد، يبحث في الملخص موسوماً `hand_written_summary`. بوابة 0.7 تبقى على الملخص فقط، لا على الاقتباس الحرفي |
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
| `pytest tests/ -q` | 179 اختباراً — منها حراسة تسجيل الأدوات، تغطية كل مصدر بأسئلة eval، قبول الموجة 1/2، وبوابات السلامة |
| مقارنة الـeval بالـbaseline المعياري | انحدار `citation_precision`/`source_recall` بأكثر من 1% → تحذير صريح |

**Evidence bundle:** `generate_release_evidence.py` ينتج `releases/<version>-evidence.json` —
مصدر الحقيقة المعلن لأي إصدار، وكل رقم فيه مسحوب من تشغيل فعلي
(git commit، عدّ manifests، pytest حقيقي، eval منفذة، بوابات مُثبتة سلوكياً).

---

## 📚 المحتوى | Content

| المجلد | المحتوى |
|--------|---------|
| `skills/` | 9 مهارات قانونية — كل ملف يبدأ بتنبيه أنه **دليل تفكير لا نص نظامي** |
| `sources/` | 20 ملخصاً نظامياً مكتوباً يدوياً (`hand_written_summary`) — كل عنوان محتوى يحمل **رابط وثيقة** (`law_document_url`) في جسمه المباشر، والبوابة وحدها لا تكفي (يتحقق آلياً باختبار سلبي). الاستثناء الوحيد: 9 مصادر `portal-only` بلا LawDetails مستقر موثق، موسومة بملصق بوابة صريح |
| `corpus/` | **النص الحرفي**: نظام العمل 245 مادة، المدنية 721، PDPL 43، لائحتها 38 — مع `fetched_at` و`sha256` ومستوى إسناد |
| `sources/manifests/` | 20 manifest JSON لكل مصدر (sha256، verification_status، مواعيد المراجعة الدورية) |
| `datasets/` | مجموعة مخاطر تعاقدية + جدول مصادر + تعريفات المجال |
| `examples/` | 14 مثال تفاعلي مع كل الأدوات |
| `prompts/` | نصوص التوجيه (الإجابة الآمنة، الصياغة المقيدة، الكشف عن المخاطر) |
| `scripts/` | generate_manifests.py (مع --check) · validate_manifests.py · verify_release.py · generate_release_evidence.py · **ingest_laws.py** · **check_boe_guids.py** · **check_source_links.py** (فحص حي للروابط الوثائقية الجديدة) · **embed_document_links.py** · **audit_section_links.py** · probe_moj_api.py · والبقية |
| `tests/` | 179 اختباراً آلياً (بدون API خارجي) — تشمل حراسة تسجيل الأدوات، قبول الموجة 1/2، بوابات السلامة، release gate، و`tests/adversarial/` (حقن الأوامر) |
| `evals/` | corpus 65 سؤالاً عبر الـ20 مصدراً + eval_runner.py — آخر أرقام: precision=97.2%، recall=90.3% |
| `releases/` | evidence bundles (`0.4.0-evidence.json`) — المصدر المعلن للحقائق لكل إصدار |
| `memory/` | دروس الجلسات الحرجة — ما تعلمه المشروع من اكتشافات الاستخدام الفعلي |

---

## 🧾 الإسناد والاقتباس | Provenance and quotes

| الحالة | ما يعنيه للمستخدم |
|---|---|
| `quotes[]` + `text_origin: official_verbatim` | نص مادة مسحوب حرفياً من صفحة رسمية، ومعه `fetched_at` و`sha256` |
| `law_document_url` | الرابط يفتح وثيقة النظام كاملة، **لا مادة محددة** |
| `direct_article_url` | رابط BOE Viewer يفتح أصل المادة الممسوح — لا مرساة نصية مخترعة |
| `portal` | بوابة عامة؛ ابحث داخلها للوصول للنص الدقيق |
| `hand_written_summary` | ملخص بشري. يُعرض كملخص، ولا يُنسب إلى النظام كاقتباس |

`answer_markdown` يُبنى في الخادم من هذه الحقول: الاقتباس، ثم الرابط، ثم تاريخ
السحب، ثم إخلاء المسؤولية. التفاصيل في [docs/corpus.md](docs/corpus.md) و
[docs/source-coverage-2026-11.md](docs/source-coverage-2026-11.md).

## 🔒 الأمان | Security

- ✅ **بدون أي مفتاح API** — السيرفر لا يتصل بأي خدمة خارجية
- ✅ **بيانات محلية** — كل الملفات نصية مقروءة محلياً، والاقتباس من `corpus/`
- ✅ **مصادر رسمية** — نصوص `corpus/` مسحوبة من boe.gov.sa و uqn.gov.sa بتاريخ ظاهر
- ✅ **مُثبَت ضد حقن الأوامر** — `tests/adversarial/`: لا SDK نموذج ولا HTTP client في الحزمة (فحص بنيوي)، ونص تعليمات محقون في مصدر يُعاد كنص عادي مع بقاء الـdisclaimer الإلزامي (إثبات سلوكي)
- ⚠️ **ليس استشارة قانونية** — للمراجعة الأولية فقط

---

## 🧱 حدود الضمان | Guarantee Boundaries

**ما يضمنه السيرفر (ويُثبته بالاختبارات):**

- أدواته **لا تختلق** — أي نتيجة تحمل `evidence[]` أو `insufficient_evidence: true`
- `text_origin` صريح: `official_verbatim` للاقتباس من `corpus/`، و`hand_written_summary` للملخص
- كل مادة في `corpus/` تحمل `fetched_at` و`sha256`، والنسخة السابقة تُحفظ عند التغيير
- الروابط تُرجع بنوعها الصريح (`portal` / `law_document_url` / `direct_article_url`)، وغيابها يُعلَن عبر `citation_note` لا يُخفى

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

> **أثمن مساهمة الآن:** رابط وثيقة رسمية ناقص، أو تشغيل `saudi-legal ingest`
> من داخل المملكة لمصدر لا يصل من CI، أو سؤال تقييم يفشل، أو تصحيح استشهاد
> لا يطابق المادة المسحوبة. المراجعة المهنية تُقبل شارة إضافية على مادة
> محددة، وليست شرطاً لاستخدام الأداة ولا لنشر إصدار.

المنظومة القانونية السعودية مشروع مفتوح المصدر. رحب بمساهماتك: إضافة أنظمة جديدة، تحسين المهارات، بيانات مخاطر، أمثلة تطبيقية.

راجع [CONTRIBUTING.md](CONTRIBUTING.md) للتفاصيل.

This is an open-source project. Contributions welcome: a missing official
document link, an ingest run from inside the Kingdom for a source CI cannot
reach, a failing eval question, or a citation that does not match the fetched
article. Professional review is an optional badge on a specific article, not a
release gate.

---

## 📄 الرخص | License

MIT License — للاستخدام الحر مع نسب المصدر والاحتفاظ بإخلاء المسؤولية القانوني.

MIT License — free to use with attribution and retention of legal disclaimer.

---

## 🔀 الفرق عن الإطار الأصلي | Difference from the original framework

هذا المستودع مشتق من [Samix2026/saudi-legal-ai-framework](https://github.com/Samix2026/saudi-legal-ai-framework):
إطار مهارات يُنسخ محتواها يدويًا في المحادثة، وخادم MCP عبر Docker بثلاث أدوات
(`analyze_contract_clause` / `get_regulation_summary` / `search_contract_risks`).
ما تغيّر هنا:

| | الإطار الأصلي | هذا المستودع |
|---|---|---|
| طريقة الاستخدام | نسخ ملف المهارة ولصقه في Claude/ChatGPT/Gemini | سيرفر MCP محلي (stdio) يعمل مع أي عميل: OpenClaw وClaude Desktop وCursor وغيرها |
| خادم MCP | Docker + 3 أدوات + `.env` | Python مباشر + **9 أدوات**، بلا Docker وبلا مفاتيح |
| النص النظامي | ملخصات مرجعية فقط | **متن حرفي** (`corpus/`: 245 + 721 + 43 + 38) مع `sha256` وتاريخ سحب |
| الإسناد | روابط عامة | تصنيف صريح: `portal` / `law_document_url` / `direct_article_url` |
| الضمان | — | بوابة إصدار + 179 اختبارًا + 65 سؤال eval (precision 97.2% / recall 90.3%) |

إن كنت تريد اللصق اليدوي في المحادثة فالأصلي يكفيك;
وإن كنت تريد استرجاعًا موثّقًا عبر MCP فهذا المستودع.

---

## 🔗 الشكر | Credits

- النسخة الأصلية: [Samix2026/saudi-legal-ai-framework](https://github.com/Samix2026/saudi-legal-ai-framework)
- هذا المستودع: [SMSMy/saudi-legal-ai](https://github.com/SMSMy/saudi-legal-ai) — نواة استرجاع MCP محلية
