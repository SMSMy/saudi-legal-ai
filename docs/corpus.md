# corpus/ — النص الحرفي ومستويات الإسناد

تاريخ الإنشاء: 2026-11-23.

هذا المجلد هو الموضع الوحيد الذي تُنتج فيه الأداة `text_origin: official_verbatim`.
ملفات `sources/` تبقى **ملخصات مكتوبة يدوياً** (`hand_written_summary`) وتُعرض
كذلك صراحةً. لا يُنسب نصٌ من `sources/` إلى النظام بوصفه اقتباساً.

## البنية

```
saudi_legal_mcp/data/corpus/
├── labor-law.json                 (هيئة الخبراء — LawDetails)
├── civil-transactions-law.json    (أم القرى — p=23125)
├── pdpl.json                      (هيئة الخبراء — LawDetails)
├── pdpl-exec-regulations.json     (أم القرى — p=23595)
└── versions/<law>/<fetched_at>.json   (نسخة سابقة، تُنشأ عند التغيير)
```

كل ملف يحمل:

```json
{
  "schema_version": "1.0",
  "law": "labor-law",
  "title_ar": "نظام العمل",
  "instrument": "المرسوم الملكي م/51 ...",
  "publisher": "هيئة الخبراء بمجلس الوزراء",
  "document_url": "https://laws.boe.gov.sa/...",
  "fetched_at": "2026-11-23T17:46:36Z",
  "fetched_by": "local",
  "source_sha256": "…",
  "article_count": 245,
  "supersedes": null,
  "articles": [
    {
      "id": "labor-law/art-84",
      "article": "84",
      "article_label": "المادة الرابعة والثمانون",
      "text": "النص الرسمي حرفياً",
      "text_origin": "official_verbatim",
      "status": "in_force | amended | added | canceled",
      "chapter": "الباب الخامس: علاقات العمل",
      "amendment_history": "…",
      "amendment_instruments": [{"instrument": "م/134", "date": "1440/11/27"}],
      "article_url": null,
      "document_url": "https://laws.boe.gov.sa/...",
      "fetched_at": "…",
      "fetched_by": "local",
      "sha256": "…"
    }
  ],
  "safety": {"empty_in_force_articles": 0, "html_tags_in_text": false, "…": "…"}
}
```

## مستويات الإسناد

| المستوى | المعنى في هذا المخزن |
|---|---|
| `linked_document` | ملخص يدوي معه رابط وثيقة النظام كاملة. |
| `fetched_official` | مادة مسحوبة من صفحة رسمية، مع `fetched_at` و`sha256`، لكن لا رابط يفتح المادة نفسها. |
| `article_level` | مادة مسحوبة **و** رابط BOE Viewer يفتح أصل المادة الممسوح. |

الغالب في `labor-law` هو `fetched_official`: معظم المواد لا تحمل رابط Viewer
مفرداً. المواد المضافة/المعدلة التي تحمل رابط Viewer (مثل 233–235) ترتفع إلى
`article_level`. لا تُخترع مراسي `#art-84`؛ الرابط الذي لا يفتح المادة لا يرفع
المستوى. لذلك `list_legal_domains` يصنّف المصدر بمستواه **الغالب** لا بأفضل
ثلاث مواد: نظام العمل `fetched_official`، مع `provenance_levels` تفصيلية
تُظهر 3 مواد `article_level` و242 مادة `fetched_official`.

## إعادة التوليد

`saudi-legal ingest` غير منفّذ بعد. السكربت الصريح هو:

```bash
# من داخل المملكة، لأن laws.boe.gov.sa محجوب عن GitHub CI
python scripts/ingest_laws.py --source labor-law
python scripts/ingest_laws.py --source pdpl
python scripts/ingest_laws.py --source pdpl-exec-regulations
python scripts/ingest_laws.py --source civil-transactions-law
```

لإعادة التحليل من صفحة محفوظة بلا شبكة:

```bash
python scripts/ingest_laws.py --source labor-law --input saved.html
```

## بوابة السلامة

قبل الكتابة يرفض السكربت الصفحة إذا:

- لم يتعرف على بنية مواد أصلاً؛
- كان عدد المواد خارج النطاق المتوقع للنظام؛
- وُجدت مادة سارية بنص فارغ؛
- بقي وسم HTML أو وسم `script/style/iframe` داخل المادة.

عند اختلاف `content_sha256` (نص المواد/حالتها/رابطها) تُنسخ النسخة السابقة إلى
`versions/` قبل الكتابة، ويُضاف `supersedes` في الملف الجديد. لا تُستبدل النسخة
القديمة في مكانها. تغيّر بصمة الصفحة وحدها (قوالب/جلسات) مع بقاء النص لا يُنشئ
نسخة جديدة؛ يُحدَّث `fetched_at` فقط.

## الأعداد الحالية (2026-11-23)

| النظام | المصدر | المواد | ملاحظات |
|---|---|---|---|
| نظام العمل | BOE `LawDetails/08381293-…` | 245 رقماً فريداً من 250 `article_item` | 3 أرقام مكررة دُمجت، وملاحظتان لترقيم قديم (240/242) لم تُعدّا مادتين. 100 معدلة + 6 مضافة = 106 (يوافق `changed-article` في الصفحة). المواد المضافة 233–235 استُخرج نصها من بين علامتي التنصيص، ويبقى تعليم النشر الأصلي في `amendment_history` (و`amendment_note` نسخة مساعدة). كل مادة معدلة/مضافة لها `amendment_instruments` و`amendment_history` (صفر بلا أداة أو تاريخ). |
| المعاملات المدنية | أم القرى `p=23125` | 721 | الأرقام متصلة 1..721، صفر فارغة. |
| PDPL | BOE `LawDetails/b7cfae89-…` | 43 | 24 مادة معدلة (`changed-article`). |
| لائحة PDPL | أم القرى `p=23595` | 38 | صفر فارغة. |

## حقوق النصوص

النصوص مسحوبة من صفحات حكومية منشورة للاطلاع العام، وتبقى حقوق النشر
والاستخدام للجهة الناشرة (هيئة الخبراء/أم القرى). المشروع لا يبيع النص ولا
يعيد ترخيصه؛ يخزّنه للاسترجاع مع الإسناد والتاريخ.

## لا شبكة داخل الحزمة

`saudi_legal_mcp` لا تستورد `requests` ولا `httpx` ولا `bs4`. السكربتات في
`scripts/` هي وحدها التي تجلب، والقراءة من المخزن المحلي فقط.
