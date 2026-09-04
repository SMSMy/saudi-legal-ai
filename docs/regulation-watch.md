# مراقبة تحديثات الأنظمة / Regulation Watch

> **تحذير:** هذا النظام يرصد **إشارات وصفية فقط** ولا يُعدّ استشارة قانونية. أي اشتباه بتغيير يتطلب تحقق محامٍ مرخّص في المملكة العربية السعودية قبل أي تعديل.
>
> **Warning:** This system observes **metadata signals only** and is not legal advice. Any suspected change requires verification by a licensed Saudi attorney before any edit.

---

## 1. المشكلة / The Problem

ملفات `sources/` توثق الأنظمة السعودية بتاريخ تحقق يدوي (`last_verified`)، لكن لا توجد آلية تنبّه عند صدور تعديل رسمي جديد — مثل تعديل نظام التحكيم (م/21 لعام 1447هـ) أو اللائحة التنفيذية لنظام حماية المبلغين (2026م). هذا المستند يصف آلية **المراقبة المتقدمة الشاملة** المعتمدة في المشروع.

`sources/` files document Saudi regulations with a manual verification date (`last_verified`), but nothing alerts when a new official amendment is issued — e.g. the Arbitration Law amendment (M/21 of 1447H) or the Whistleblower Law executive regulation (2026). This document describes the project's **advanced comprehensive watch** mechanism.

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
│ laws.boe.gov.sa (صفحات LawDetails) + laws.moj.gov.sa  │  ← النص المعتمد
├─ Layer 2 · الجريدة الرسمية ───────────────────────────┤
│ uqn.gov.sa (أم القرى — النشر الرسمي للتعديلات)         │  ← سريان التعديل
├─ Layer 3 · الإنذار المبكر ────────────────────────────┤
│ istitlaa.ncc.gov.sa (مشاريع الأنظمة قبل إقرارها)      │  ← تعديلات قادمة
├─ Layer 4 · البوابات القطاعية + البيانات المفتوحة ─────┤
│ ZATCA (موجات الفوترة) · SDAIA · GAC · SAIP · HRSD/    │  ← لوائح وموجات
│ قوى · SBA · REAC · SAFF (موسمية) · FIFA · data.gov.sa │
└───────────────────────────────────────────────────────┘
```

- **Layer 1–2** يكشفان التعديل **بعد** صدوره (مصدر الحقيقة).
- **Layer 3** يكشف التعديل **قبل** صدوره (مشروع معروض للاستشارة → استعد للمراجعة).
- **Layer 4** يكشف تحديثات اللوائح والموجات التي لا تصدر بمرسوم ملكي (ZATCA، SAFF الموسمية).

> **بصراحة التوثيق:** ليست كل الطبقات مفعّلة لكل مدخل. الفاحص يضرب فقط الحقول الموجودة فعلًا في السجل (`url` + `gazette_url` + `istitlaa_url` + `sector_feed`) — والحقل الغائب يُتخطى ولا يُخترع له رابط. روابط `gazette_url` المباشرة موثقة حاليًا لمدخل واحد (`whistleblower_law` → `uqn.gov.sa/details?p=24614`)؛ البقية تُضاف فور توثيقها من `uqn.gov.sa`. المدخلات بثقة `portal` (صفحات رئيسية) إشارتها ضعيفة بالاتجاهين: تغيّرها يُسجَّل `PORTAL_CHANGED` للمعلومية فقط ولا يفتح Issue.

---

## 4. المكونات / Components

| الملف | الدور |
|---|---|
| [`evals/source-registry.json`](../evals/source-registry.json) | السجل الآلي المقروء (schema v2.1): 20 مدخلًا، كل مدخل: `url` + `gazette_url` (إن وُجد) + `istitlaa_url` (إن وُجد) + `sector_feed` + `citation` المطابقة لـ `regulation-index.md` |
| [`scripts/check_regulation_updates.py`](../scripts/check_regulation_updates.py) | الفاحص (v2): طلبات HEAD (ترويسات فقط)، **بصمة مستقلة لكل URL**، ترجيح الثقة (`exact` → SUSPECT، `portal` → PORTAL_CHANGED للمعلومية)، حدّ معدل 1.5s، توقف عند 429 |
| [`evals/.regulation-watch-state.json`](../evals/.regulation-watch-state.json) | خط الأساس لكل URL: يُنشأ تلقائيًا، ويُجمَّد فقط عند وجود SUSPECT معلق (الأعلام الداخلية لا تجمّده) |
| [`.github/workflows/regulation-watch.yml`](../.github/workflows/regulation-watch.yml) | التشغيل الأسبوعي (الأحد 06:00 UTC = 09:00 KSA) + تشغيل يدوي: ضمان الـlabels + منع تكرار الـIssues (تعليق على المفتوحة بدل التكرار) + تقرير artifact + تحديث خط الأساس عند النظافة فقط |
| [`.github/ISSUE_TEMPLATE/legal-source-reference.yml`](../.github/ISSUE_TEMPLATE/legal-source-reference.yml) | نموذج التحقق البشري لكل تغيير مؤكد |

**التوافق العكسي:** الحقول الأصلية `name/decree/date/url` للمدخلات الخمسة الأولى محفوظة حرفيًا — `evals/validate_cases.py` يعمل دون تغيير.

**Backward compatibility:** the original five entries' `name/decree/date/url` fields are preserved verbatim — `evals/validate_cases.py` works unchanged.

---

## 5. حالات النتيجة / Result States

| الحالة | المعنى | الإجراء |
|---|---|---|
| `OK` | لا تغيّر في أي إشارة | لا شيء |
| `NEW` | أول رصد (تأسيس خط الأساس) | معلومة فقط |
| `SUSPECT` | تغيّرت إشارة بثقة `exact` (صفحة نظام / جريدة / وثيقة مسماة) | تحقق بشري فوري — Issue تلقائية (بلا تكرار) |
| `PORTAL_CHANGED` | تحركت إشارة بوابة `portal` فقط (ضجيج محتمل) | للمعلومية — لا Issue إلا بتكرار النمط عبر أسابيع |
| `UNREACHABLE` | تعذّر الوصول (شبكة/SSL/WAF) | **ليست** إشارة تغيير — تُعاد المحاولة تلقائيًا |
| `SKIPPED` | تخطٍّ بعد حدّ المعدل 429 | تُعاد الجدولة |

الأعلام الداخلية (`known_amendment_note` / `known_discrepancy_note`) **ليست حالة** — تظهر في قسم مستقل بالتقرير (تقرير فقط): لا تغيّر الحالة، لا تمنع حفظ الأساس، ولا تفتح Issue.

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
2. **شغّل يدويًا مرة:** Actions → Regulation Watch → Run workflow. تحقق من: التقرير (artifact) + `evals/.regulation-watch-state.json` + Issue (إن وُجد SUSPECT).
3. **الـlabels تُنشأ تلقائيًا** (`legal-source` + `content-update`) قبل إنشاء أي Issue — لا حاجة لإنشائها يدويًا.
4. **بلا تكرار:** إن وُجدت Issue مفتوحة بنفس العنوان، يُعلَّق عليها بالتقرير الجديد بدل فتح مكررة. أغلقها يدويًا بعد توثيق قرار التحقق ثم حدّث الأساس (`--update-state`).

---

## 7. دورة المعالجة البشرية / Human Handling Lifecycle

```
SUSPECT (Issue تلقائية، بلا تكرار)
        │
        ▼
محامٍ مرخّص يقارن: رقم المرسوم + نص المادة
boe.gov.sa ←→ sources/regulation-index.md ←→ sources/…md
        │
        ├── مؤكد ──► حدّث regulation-index.md أولًا
        │            ثم sources/…md، ثم datasets
        │            (deprecated/superseded حسب docs/legal-verification-lifecycle.md)
        │            ثم PR بالروابط الرسمية
        │            ثم --update-state
        │
        └── غير مؤكد (ضجيج تقني) ──► وثّق في الـ Issue
                                     ثم --update-state لتحديث البصمة
```

---

## 8. القيود المعروفة / Known Limitations

1. **الحمايات التقنية للمواقع الحكومية** (WAF / شهادات SSL في بعض البيئات) قد تُظهر `UNREACHABLE` — وهذا **ليس** دليل تغيير. السكربت لا يفرّق بين الحجب والتعديل عمدًا، بل يترك القرار للبشر.
2. **البوابات الثقيلة بجافاسكربت** (بعض صفحات boe) لا تعيد `ETag/Last-Modified` — عندها يعتمد الكشف على `status/final-URL/length` مع `sector_feed` الاحتياطي المسجل لكل مدخل.
3. **منصة استطلاع** تُراقَب كروابط مرجعية للمراجعة البشرية (مشاريع مطروحة)، لا ككشط آلي — التزامًا بسياسة `docs/official-api-sources.md` (يُحظر الكشط غير المرخّص).
4. **SAFF/FIFA** لوائح موسمية/دولية — الإشارة هنا تنبيه بنشر ملفات جديدة قبل كل موسم، لا حكمًا قانونيًا.
5. **المراقب يقول «ترويسات الصفحة تغيّرت أو لا» — لا يقول «المادة 24 ما زالت كما هي».** البوابات خلف WAF قد لا تعطي `ETag/Last-Modified` مفيدًا، وصفحة `LawDetails` قد تكون غلاف JavaScript لا تتحرك بصمته بتغيّر قاعدة البيانات. لذلك: الثقة الكاملة تتطلب **طبقة الثقة** اللاحقة (أرشفة نص المادة + بطاقة صلاحية على كل جواب + صمت عند غياب السند) — وهي خارج نطاق هذا المراقب عمدًا.

---

## 9. الملفات المرتبطة / Related Files

| الملف | العلاقة |
|---|---|
| [`sources/regulation-index.md`](../sources/regulation-index.md) | المصدر البشري الوحيد لصيغ الاستشهاد — يُحدَّث أولًا عند أي تعديل مؤكد |
| [`docs/official-api-sources.md`](official-api-sources.md) | السياسة الحاكمة: لا كشط غير مرخّص، APIs المرخّصة فقط |
| [`docs/legal-verification-lifecycle.md`](legal-verification-lifecycle.md) | حالات `deprecated` / `superseded` للصفوف المتأثرة بتعديل |
| [`tests/test_regulation_watch.py`](../tests/test_regulation_watch.py) | 25 اختبارًا — كل الشبكات محاكاة، لا HTTP حقيقي |
