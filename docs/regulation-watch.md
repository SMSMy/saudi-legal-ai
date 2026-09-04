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
| ترصد تغيّر الإشارات الوصفية (HTTP status / final URL / ETag / Last-Modified / Content-Length) لصفحات الأنظمة الرسمية | لا تنسخ أي نص قانوني ولا تفسّره |
| ترفع إشعارًا داخليًا عند الاشتباه (Issue تلقائية + تقرير أسبوعي) | لا تعدّل `sources/` أو `datasets/` تلقائيًا أبدًا |
| تجمع الإنذار المبكر من منصة استطلاع (مشاريع تعديل معروضة للعموم) والجريدة الرسمية | لا تعتبر عدم الوصول (حجب/SSL/WAF) دليلًا على تغيير قانوني |
| توثق خط الأساس (fingerprint) لكل نظام لتكشف التغيّر عبر الأسابيع | لا تغني عن مراجعة المحامي المرخّص |

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

---

## 4. المكونات / Components

| الملف | الدور |
|---|---|
| [`evals/source-registry.json`](../evals/source-registry.json) | السجل الآلي المقروء: 20 مدخلًا (14 نظامًا + تنفيذيات + لوائح قطاعية/رياضية)، كل مدخل: `url` + `sector_feed` + `citation` المطابقة لـ `regulation-index.md` + `monitor.signals` |
| [`scripts/check_regulation_updates.py`](../scripts/check_regulation_updates.py) | الفاحص: طلبات HEAD (ترويسات فقط، لا يقرأ الجسم أبدًا)، بصمة `sha256(status\|url\|etag\|last-modified\|length)`، حدّ معدل 1.5s، توقف عند 429 |
| [`evals/.regulation-watch-state.json`](../evals/.regulation-watch-state.json) | خط الأساس: يُنشأ تلقائيًا عند أول تشغيل نظيف، يُجمَّد عند وجود إشارات معلقة |
| [`.github/workflows/regulation-watch.yml`](../.github/workflows/regulation-watch.yml) | التشغيل الأسبوعي (الأحد 06:00 UTC = 09:00 KSA) + تشغيل يدوي: تقرير artifact + Issue تلقائية عند الاشتباه + تحديث خط الأساس عند النظافة فقط |
| [`.github/ISSUE_TEMPLATE/legal-source-reference.yml`](../.github/ISSUE_TEMPLATE/legal-source-reference.yml) | نموذج التحقق البشري لكل تغيير مؤكد |

**التوافق العكسي:** الحقول الأصلية `name/decree/date/url` للمدخلات الخمسة الأولى محفوظة حرفيًا — `evals/validate_cases.py` يعمل دون تغيير.

**Backward compatibility:** the original five entries' `name/decree/date/url` fields are preserved verbatim — `evals/validate_cases.py` works unchanged.

---

## 5. حالات النتيجة / Result States

| الحالة | المعنى | الإجراء |
|---|---|---|
| `OK` | لا تغيّر في الإشارات | لا شيء |
| `NEW` | أول رصد (تأسيس خط الأساس) | معلومة فقط |
| `SUSPECT` | تغيّرت البصمة الوصفية | تحقق بشري فوري — Issue تلقائية |
| `NEEDS_HUMAN_REVIEW` | علَم داخلي موثق (تعديل معروف غير مؤكد، فرق تاريخ، لائحة موسمية) | تحقق محامٍ قبل أي تعديل |
| `UNREACHABLE` | تعذّر الوصول (شبكة/SSL/WAF) | **ليست** إشارة تغيير — تُعاد المحاولة تلقائيًا |
| `SKIPPED` | تخطٍّ بعد حدّ المعدل 429 | تُعاد الجدولة |

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

رموز الخروج: `0` نظيف · `1` توجد إشارات تستلزم مراجعة · `2` عطل بنية تحتية شامل.

---

## 7. دورة المعالجة البشرية / Human Handling Lifecycle

```
SUSPECT / NEEDS_HUMAN_REVIEW (Issue تلقائية)
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

---

## 9. الملفات المرتبطة / Related Files

| الملف | العلاقة |
|---|---|
| [`sources/regulation-index.md`](../sources/regulation-index.md) | المصدر البشري الوحيد لصيغ الاستشهاد — يُحدَّث أولًا عند أي تعديل مؤكد |
| [`docs/official-api-sources.md`](official-api-sources.md) | السياسة الحاكمة: لا كشط غير مرخّص، APIs المرخّصة فقط |
| [`docs/legal-verification-lifecycle.md`](legal-verification-lifecycle.md) | حالات `deprecated` / `superseded` للصفوف المتأثرة بتعديل |
| [`tests/test_regulation_watch.py`](../tests/test_regulation_watch.py) | 17 اختبارًا — كل الشبكات محاكاة، لا HTTP حقيقي |
