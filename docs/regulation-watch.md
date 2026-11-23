# مراقبة تحديثات الأنظمة / Regulation Watch

> **تحذير:** هذا النظام يرصد **إشارات وصفية فقط** ولا يُعدّ استشارة قانونية. أي اشتباه بتغيير يتطلب تحقق محامٍ مرخّص في المملكة العربية السعودية قبل أي تعديل.
>
> **Warning:** This system observes **metadata signals only** and is not legal advice. Any suspected change requires verification by a licensed Saudi attorney before any edit.

---

## 1. المشكلة / The Problem

ملفات `saudi_legal_mcp/data/sources/` توثق الأنظمة السعودية بتاريخ تحقق يدوي (`last_verified`)، لكن لا توجد آلية تنبّه عند صدور تعديل رسمي جديد — مثل تعديل نظام التحكيم (م/21 لعام 1447هـ) أو اللائحة التنفيذية لنظام حماية المبلغين (2026م). هذا المستند يصف آلية **المراقبة المتقدمة الشاملة** المعتمدة في المشروع.

`saudi_legal_mcp/data/sources/` files document Saudi regulations with a manual verification date (`last_verified`), but nothing alerts when a new official amendment is issued — e.g. the Arbitration Law amendment (M/21 of 1447H) or the Whistleblower Law executive regulation (2026). This document describes the project's **advanced comprehensive watch** mechanism.

---

## 2. ماذا تفعل الآلية وماذا لا تفعل / What It Does and Does Not Do

| تفعل / Does | لا تفعل / Does not do |
|---|---|
| ترصد تغيّر الإشارات الوصفية (HTTP status / final URL / ETag / Last-Modified / Content-Length) **لكل URL مراقَب على حدة** (صفحة نظام، جريدة، وثيقة استطلاع، بوابة قطاعية) | لا تنسخ أي نص قانوني ولا تفسّره |
| ترفع Issue تلقائية **فقط** عند تغيّر إشارة بثقة `exact` (صفحة نظام / جريدة / وثيقة مسماة) | لا تفتح Issue لضجيج البوابات (`portal`) ولا للأعلام الداخلية الثابتة |
| تسجل الأعلام الداخلية المعروفة في التقرير كقسم مستقل (تقرير فقط) | لا تجمّد خط الأساس بسببها ولا تعتبرها اشتباهًا أسبوعيًا |
| توثق خط الأساس لكل URL لتكشف التغيّر عبر الأسابيع | لا تغني عن مراجعة المحامي المرخّص |

---

## 3. طبقات الإشارة الأربع / The Four Signal Layers

```
┌─ Layer 1 · صفحات الأنظمة ─────────────────────────────┐
│ laws.moj.gov.sa (بوابة العدل — تصل من CI)             │  ← النص المعتمد
│ laws.boe.gov.sa (LawDetails — مرجع boe_reference_url، │
│ محجوب عن CI، يصل من داخل المملكة)                     │
├─ Layer 2 · الجريدة الرسمية ───────────────────────────┤
│ uqn.gov.sa (أم القرى — النشر الرسمي للتعديلات)         │  ← سريان التعديل
├─ Layer 3 · الإنذار المبكر ────────────────────────────┤
│ istitlaa (انتقلت من ncc.gov.sa إلى scbc.gov.sa —      │
│ الروابط القديمة متقاعدة؛ تُوثق بدائل عند ظهورها)      │  ← تعديلات قادمة
├─ Layer 4 · البوابات القطاعية + البيانات المفتوحة ─────┤
│ ZATCA (موجات الفوترة) · GAC · SAIP · HRSD/قوى · SBA · │  ← لوائح وموجات
│ REAC · SAFF (موسمية) · FIFA · SADR (التحكيم)          │
└───────────────────────────────────────────────────────┘
```

- **Layer 1–2** يكشفان التعديل **بعد** صدوره (مصدر الحقيقة).
- **Layer 3** يكشف التعديل **قبل** صدوره (مشروع معروض للاستشارة → استعد للمراجعة).
- **Layer 4** يكشف تحديثات اللوائح والموجات التي لا تصدر بمرسوم ملكي (ZATCA، SAFF الموسمية).

> **بصراحة التوثيق (بعد #14، 2026-11-23):** ليست كل الطبقات مفعّلة لكل مدخل. الفاحص يضرب فقط الحقول الموجودة فعلًا في السجل (`url` + `gazette_url` + `istitlaa_url` + `sector_feed`) — والحقل الغائب يُتخطى ولا يُخترع له رابط. **كل مدخل له الآن هدف واحد على الأقل يصل من CI**: بوابة العدل `laws.moj.gov.sa/ar` (ثقة `portal` — تخفيض صادق موثّق لأن صفحات BOE الدقيقة محجوبة عن العدّاء)، أو رابط الجريدة `uqn.gov.sa` الموثق (يبقى `exact`: المبلغين، تنفيذية PDPL)، أو وثيقة قطاعية مسماة (ZATCA PDF المحدّث 20230519، REAC، SAFF). روابط BOE الأصلية (14 نظامًا) محفوظة كمرجع غير مراقَب في `boe_reference_url` — لا تُحذف ولا تُراقَب من CI. المدخلات بثقة `portal` إشارتها ضعيفة بالاتجاهين: تغيّرها يُسجَّل `PORTAL_CHANGED` للمعلومية فقط ولا يفتح Issue. انظر جدول التغطية في §10.

---

## 4. المكونات / Components

| الملف | الدور |
|---|---|
| [`evals/source-registry.json`](../evals/source-registry.json) | السجل الآلي المقروء (schema v2.2): 20 مدخلًا، كل مدخل: `url` + `gazette_url` (إن وُجد) + `istitlaa_url` (إن وُجد) + `sector_feed` + `boe_reference_url` (مرجع BOE غير مراقَب) + `citation` المطابقة لـ `regulation-index.md` |
| [`scripts/check_regulation_updates.py`](../scripts/check_regulation_updates.py) | الفاحص (v2.1): طلبات HEAD (ترويسات فقط)، **بصمة مستقلة لكل URL**، ترجيح الثقة (`exact` → SUSPECT، `portal` → PORTAL_CHANGED للمعلومية)، حدّ معدل 1.5s، توقف عند 429، **HTTP ≥ 400 → PROBE_ERROR لا يُخزَّن كخط أساس** (#14) |
| [`evals/.regulation-watch-state.json`](../evals/.regulation-watch-state.json) | خط الأساس لكل URL: يُنشأ تلقائيًا، ويُجمَّد فقط عند وجود SUSPECT معلق (الأعلام الداخلية لا تجمّده) |
| [فرع `regulation-watch-state`](https://github.com/SMSMy/saudi-legal-ai-openclaw/tree/regulation-watch-state) | مكان حفظ الأساس الفعلي — فرع مستقل غير محمي، لأن `main` محمي ضد دفع البوت (GH013). كل تشغيل يسترجع الأساس منه، ويدفع فوق رأسه مباشرة (fast-forward، لا `checkout -B` أبدًا حتى لا يتشعب التاريخ وينكسر الدفع التالي). الدفع مشروط بتغيّر بصمات الـURLs فعلًا (`signals_snapshot`) — دوران العدّادات وحده (`last_seen` / `consecutive_unreachable`) لا يستحق commit أسبوعيًا |
| [`.github/workflows/regulation-watch.yml`](../.github/workflows/regulation-watch.yml) | التشغيل الأسبوعي (الأحد 06:00 UTC = 09:00 KSA) + تشغيل يدوي: ضمان الـlabels + منع تكرار الـIssues (تعليق على المفتوحة بدل التكرار) + تقرير artifact + تحديث خط الأساس عند النظافة فقط |
| [`.github/ISSUE_TEMPLATE/legal-source-reference.yml`](../.github/ISSUE_TEMPLATE/legal-source-reference.yml) | نموذج التحقق البشري لكل تغيير مؤكد |

**حفظ المراجع:** روابط BOE الأصلية محفوظة حرفيًا في `boe_reference_url` (مرجع توثيقي غير مراقَب) — أي مراجعة بشرية أو تحقق من داخل المملكة تبدأ منها. الحقول `name/decree/date/citation` محفوظة حرفيًا كبيانات استشهاد.

**Reference preservation:** the original BOE links are preserved verbatim in `boe_reference_url` (an unmonitored documentary reference) — human verification from inside the Kingdom starts there. `name/decree/date/citation` fields are preserved verbatim as citation metadata.

---

## 5. حالات النتيجة / Result States

| الحالة | المعنى | الإجراء |
|---|---|---|
| `OK` | لا تغيّر في أي إشارة | لا شيء |
| `NEW` | أول رصد (تأسيس خط الأساس) | معلومة فقط |
| `SUSPECT` | تغيّرت إشارة بثقة `exact` (صفحة نظام / جريدة / وثيقة مسماة) | تحقق بشري فوري — Issue تلقائية (بلا تكرار) |
| `PORTAL_CHANGED` | تحركت إشارة بوابة `portal` فقط (ضجيج محتمل) | للمعلومية — لا Issue إلا بتكرار النمط عبر أسابيع |
| `URL_RETIRED` | الرابط المراقَب لم يعد يخدم المورد: صفحة خطأ/دخول، أو 404/410، أو رابط مستند (`.pdf`/`.doc`/`.docx`) صار يخدم HTML | **انقطاع تتبّع لا إشارة تعديل** — لا Issue، ولا يجمّد الأساس؛ يلزم توثيق رابط بديل بشريًا، والمصدر يبقى فعليًا بلا مراقبة حتى ذلك |
| `PROBE_ERROR` | كل الردود أخطاء خادم (HTTP ≥ 400 مثل 400/403/500) وليست روابط متقاعدة | **خطأ مسبار لا مورد حي** (#14): لا يُخزَّن كخط أساس محتوى، لا يُقرأ نجاحًا صامتًا، لا يفتح Issue ولا يجمّد الأساس — يظهر في قسم Probe Errors؛ يُعاد المحاولة لاحقًا أو يُوثق بديل |
| `UNREACHABLE` | تعذّر الوصول (شبكة/SSL/WAF) | **ليست** إشارة تغيير — تُعاد المحاولة تلقائيًا |
| `SKIPPED` | تخطٍّ بعد حدّ المعدل 429 | تُعاد الجدولة |

الأعلام الداخلية (`known_amendment_note` / `known_discrepancy_note`) **ليست حالة** — تظهر في قسم مستقل بالتقرير (تقرير فقط): لا تغيّر الحالة، لا تمنع حفظ الأساس، ولا تفتح Issue.

**تقاعد portal لا يمر صامتًا (#14):** رابط بوابة متقاعد (404/410/صفحة خطأ) يظهر في قسم Retired Links حتى لو كانت الروابط الدقيقة للمدخل حية ولم ترتفع حالة `URL_RETIRED`.

---

## 6. الاستخدام المحلي / Local Usage

```bash
pip install requests   # أو: pip install -r requirements-dev.txt

# فحص دون شبكة — الأعلام الداخلية فقط (سريع، للمساهمين)
python3 scripts/check_regulation_updates.py --offline

# فحص حي كامل + تقرير Markdown
python3 scripts/check_regulation_updates.py --check --report regulation-watch-report.md

# بعد توثيق قرار التحقق البشري فقط — تحديث خط الأساس
python3 scripts/check_regulation_updates.py --check --update-state

# مخرجات آلية للربط مع أدوات أخرى
python3 scripts/check_regulation_updates.py --check --json
```

رموز الخروج: `0` لا SUSPECT · `1` يوجد SUSPECT · `2` عطل بنية تحتية شامل.

---

## 6.1. قائمة التشغيل الأول / First-Run Checklist

1. **فعّل Actions** في المستودع (Settings → Actions → Allow all actions). الـcron يعمل تلقائيًا في المستودعات العامة النشطة، لكن أول تشغيل يجب أن يكون يدويًا.
2. **شغّل يدويًا مرة:** Actions → Regulation Watch → Run workflow. تحقق من: التقرير (artifact) + فرع `regulation-watch-state` (الأساس) + Issue (إن وُجد SUSPECT). لا تتوقع ملف الأساس على `main` — الفرع المستقل هو مكانه بسبب حماية `main` (GH013).
3. **توقع BOE غير قابل للوصول من CI** (ConnectTimeout مثبت 2026-09-04) — الـUNREACHABLE على نطاق `laws.boe.gov.sa` ضجيج شبكة معروف، لا إشارة.
3. **الـlabels تُنشأ تلقائيًا** (`legal-source` + `content-update`) قبل إنشاء أي Issue — لا حاجة لإنشائها يدويًا.
4. **بلا تكرار:** إن وُجدت Issue مفتوحة بنفس العنوان، يُعلَّق عليها بالتقرير الجديد بدل فتح مكررة. أغلقها يدويًا بعد توثيق قرار التحقق ثم حدّث الأساس (`--update-state`).

---

## 7. دورة المعالجة البشرية / Human Handling Lifecycle

```
SUSPECT (Issue تلقائية، بلا تكرار)
        │
        ▼
محامٍ مرخّص يقارن: رقم المرسوم + نص المادة
boe.gov.sa ←→ saudi_legal_mcp/data/sources/regulation-index.md ←→ ملف المصدر
        │
        ├── مؤكد ──► حدّث regulation-index.md أولًا
        │            ثم ملف المصدر، ثم datasets
        │            (deprecated/superseded حسب دورة حياة التحقق في المستودع الأصلي)
        │            ثم PR بالروابط الرسمية
        │            ثم --update-state
        │
        └── غير مؤكد (ضجيج تقني) ──► وثّق في الـ Issue
                                     ثم --update-state لتحديث البصمة
```

---

## 8. القيود المعروفة / Known Limitations

1. **الحمايات التقنية للمواقع الحكومية** (WAF / شهادات SSL في بعض البيئات) قد تُظهر `UNREACHABLE` — وهذا **ليس** دليل تغيير. السكربت لا يفرّق بين الحجب والتعديل عمدًا، بل يترك القرار للبشر.
2. **نتيجة حية موثقة (2026-09-04): `laws.boe.gov.sa` لا يرد أصلًا من عدّائي GitHub** — كل صفحات LawDetails سقطت بـ ConnectTimeout (غالبًا ترشيح جغرافي). بعد #14: الروابط محفوظة في `boe_reference_url` والتغطية الفعلية من CI تأتي من بوابة العدل (`laws.moj.gov.sa` تستجيب 200) والجريدة والوثائق القطاعية المسماة. التشغيل المحلي من داخل المملكة قد يصل لـ BOE مباشرة — قارن تقريرك المحلي بتقرير CI (جدول §10).
3. **BOE تدوّر معرّفات الصفحات أحيانًا**: صفحة نظام الشركات انتقلت من `10d19e91` إلى `a8376aea` (اكتُشف 2026-09-04 عبر الفهرسة). أي تدوير مشابه لاحقًا يتطلب تحديث `boe_reference_url` في السجل.
4. **البوابات الثقيلة بجافاسكربت** لا تعيد `ETag/Last-Modified` مفيدًا — عندها يعتمد الكشف على `status/final-URL/length` مع `sector_feed` الاحتياطي المسجل لكل مدخل.
5. **منصة استطلاع** تُراقَب كروابط مرجعية للمراجعة البشرية (مشاريع مطروحة)، لا ككشط آلي — التزامًا بسياسة عدم الكشط غير المرخّص. تنبيه: نطاق `istitlaa.ncc.gov.sa` انتقل إلى `istitlaa.scbc.gov.sa` والمسارات القديمة تخدم صفحات خطأ — لا تُخزَّن كخط أساس.
6. **SAFF/FIFA** لوائح موسمية/دولية — الإشارة هنا تنبيه بنشر ملفات جديدة قبل كل موسم، لا حكمًا قانونيًا. **تنبيه ثقة:** فهرس وثائق دولي يبني نفسه بجافاسكربت (`no-store`، `HEAD 405`، ETag يتبدّل أسبوعيًا) **ليس «وثيقة مسماة» بثقة `exact`** — لذلك `fifa_rstp` مُسجَّل `portal` عمدًا (تخفيض إشارة، لا تغيير هدف). يُعاد النظر فقط عند توثيق رابط ملف RSTP **مستقر**.
7. **المراقب يقول «ترويسات الصفحة تغيّرت أو لا» — لا يقول «المادة 24 ما زالت كما هي».** الثقة الكاملة تتطلب **طبقة الثقة** اللاحقة (أرشفة نص المادة + بطاقة صلاحية على كل جواب + صمت عند غياب السند) — وهي خارج نطاق هذا المراقب عمدًا.
8. **أخطاء الخادم ليست موارد (#14):** أي رد HTTP ≥ 400 (400/403/500…) يُصنَّف `PROBE_ERROR` ولا يُخزَّن كخط أساس محتوى ولا يُقرأ نجاحًا صامتًا. قبل v2.1 كان الخطأ 500 يُخزَّن كإشارة حية، فأول رد 200 يرفع SUSPECT كاذبًا (500→200) ثم يعود 500 فيرفع آخر — والصمت يبدو سلامة.
9. **الفشل الشبكي يحذف البصمة القديمة عمدًا** (حتى لا تُقارن صفحة خطأ بأساس قديم وتُقرأ تعديلًا). أثر جانبي موثق: أول رد ناجح بعد فشل عابر يُسجَّل كخط أساس «جديد» (fresh) بلا SUSPECT — قد يمر انتقال حالة عبر فشل عابر. راقب قسم Probe Errors وتاريخ فرع الحالة عند الشك؛ تجميد الأساس عند SUSPECT ما زال قائمًا.

---

## 9. الملفات المرتبطة / Related Files

| الملف | العلاقة |
|---|---|
| [`saudi_legal_mcp/data/sources/regulation-index.md`](../saudi_legal_mcp/data/sources/regulation-index.md) | المصدر البشري الوحيد لصيغ الاستشهاد — يُحدَّث أولًا عند أي تعديل مؤكد |
| [`docs/official-api-sources.md` (المستودع الأصلي)](https://github.com/Samix2026/saudi-legal-ai-framework/blob/main/docs/official-api-sources.md) | السياسة الحاكمة: لا كشط غير مرخّص، APIs المرخّصة فقط |
| [`docs/legal-verification-lifecycle.md` (المستودع الأصلي)](https://github.com/Samix2026/saudi-legal-ai-framework/blob/main/docs/legal-verification-lifecycle.md) | حالات `deprecated` / `superseded` للصفوف المتأثرة بتعديل |
| [`tests/test_regulation_watch.py`](../tests/test_regulation_watch.py) | اختبارات الفاحص — كل الشبكات محاكاة، لا HTTP حقيقي |

---

## 10. التغطية الفعلية: CI مقابل داخل المملكة / Effective Coverage (after #14)

| الطبقة | من عدّائي GitHub (CI) | من داخل المملكة |
|---|---|---|
| بوابة العدل `laws.moj.gov.sa/ar` | ✅ تصل (200 مثبت في تقارير CI) — الهدف المراقَب لـ 10 أنظمة بثقة portal | ✅ تصل |
| الجريدة `uqn.gov.sa` (رابطا المبلغين وتنفيذية PDPL) | ✅ تصل (200؛ كانت 500 في سبتمبر 2026 وأصلحها الخادم) — exact | ✅ تصل |
| وثائق قطاعية مسماة: ZATCA PDF المحدّث 20230519، REAC، SAFF | ✅ تصل (200 application/pdf للـZATCA، موثق 2026-11-23) — exact | ✅ تصل |
| بوابات قطاعية: SAIP، SBA، SADR، GAC، MC، HRSD، FIFA | ✅/⚠️ تصل غالبًا؛ HRSD يرد 403 أحيانًا وpp.gov.sa يرد 400 على HEAD → PROBE_ERROR ظاهر لا صامت | ✅ تصل غالبًا |
| صفحات BOE الدقيقة (LawDetails) | ❌ محجوبة (ConnectTimeout) — محفوظة `boe_reference_url` غير مراقَبة | ✅ قد تصل مباشرة (بعض الصفحات يحوّلها BOE إلى /Error أو /Account/Login — تحقق بشري) |
| istitlaa (المسارات القديمة ncc) | ❌ متقاعدة (302 → scbc → صفحة خطأ) — حُذفت من الأهداف | ❌ متقاعدة أيضًا |

**الخلاصة:** صفر `SUSPECT` لا يعني أن الأنظمة لم تتغيّر — يعني أن الطبقة الوصفية لم ترصد تغيّرًا في الأهداف التي تصل إليها. أي قرار تشريعي يبقى بيد مختص قانوني مرخّص.
