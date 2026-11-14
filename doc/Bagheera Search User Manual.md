# Bagheera Search User Manual

## 1. Introduction

**Bagheera Search** is a high-performance search utility and library that enhances the standard **KDE Baloo** search experience. It allows users to locate files using a combination of file metadata, hierarchical tags, and advanced logical expressions.

## 2. Command Line Interface (CLI)

The primary way to interact with the search engine is via the `bagheerasearch` command.

### Basic Usage

```bash
bagheerasearch "your query terms" [options]
```

### Global Options

- `--help-query`: Shows detailed help regarding the supported query syntax.
- `--type [type]`: Filters results by file type (e.g., `image`, `video`, `audio`).
- `--id`: Displays document IDs.
- `--konsole`: Displays files using the `file:/` protocol and quotes.
- `--year [YYYY]`: Filters results by a specific year.
- `--month [MM]`: Filters results by month (requires `--year`).
- `--day [DD]`: Filters results by day (requires `--year` and `--month`).
- `--version`: Displays the current version of the **Bagheera Search**.

For more options, please consult the CLI help (`--help`).

---

## 3. Query Syntax

**Bagheera** Search supports Baloo's rich query syntax for keyword matching. Additionally, the `having` options support an even more advanced syntax for fine-grained filtering.

```text
query [HAVING expression] [[operator] SUBQUERY [query] [HAVING expression]]...
```

Each `HAVING` filters the immediately preceding search; an empty `HAVING` is
ignored and repeated `HAVING` clauses in a search are joined with `AND`.
An empty `SUBQUERY` searches all items in the folders selected by the main query. Clause names and
operators are uppercase. Options can be interspersed with the query:
after an option and its value, text continues in the current section. The whole
query may also be passed as a single quoted argument. Preserve inner quotes
where needed for literal values and quote shell operators such as `>` and `(`.
For example, `bagheerasearch 'filename="HAVING" SUBQUERY'` searches for the
literal value `HAVING` in the main query. The old `--having`, `--subquery`, and
`--subquery-having` options and their short aliases are no longer supported.

### Logical Operators

Combine multiple criteria using uppercase logical operators:

- `AND`: Both conditions must be true.
- `OR`: At least one condition must be true.
- `NOT`: Inverts the following condition (only available within `having` options).
- `(...)`: Use parentheses to group expressions and define the order of evaluation.

**Example:** `bagheerasearch 'type=images AND modified>=2025-01-01 AND (tags:vacaciones OR tags:summer) HAVING NOT (tags:work OR tags:trabajo)'`

### Property Filters

Filter by specific file metadata using the `property <operator> value` syntax. When using having options, you can also use `property <operator> property` to compare two different metadata fields.

| Property   | Description                                                                       |
| ---------- | --------------------------------------------------------------------------------- |
| `tags`     | Keywords or labels assigned to the file.                                          |
| `rating`   | File rating (from 1 to 10).                                                       |
| `filename` | The name of the file.                                                             |
| `height`   | Image height in pixels.                                                           |
| `width`    | Image width in pixels.                                                            |
| `type`     | The file **Baloo** type (a full list of available types is provided in Chapter 6) |
| `mimetype` | The file mimetype (e.g., `jpeg`).                                                 |

A full list of available properties is provided in Chapter 7.

### Comparison Operators

**Bagheera** supports various ways to compare values:

- `=`: Equals.
- `==`: Strict equality (case-sensitive), available only with `having` options or equal comparison on date properties to avoid hour/minute/second comparison.
- `!=`: Not equal, available only with `having` options.
- `>` / `<`/ `>=`/ `<=`: Greater than, less than, greater than or equal to, less than or equal to (for numeric values and dates).
- `:`:  Contains or starts with (case-insensitive).
- `!:`: Does not contain, available only with `having` options.

**Examples:**

- **Find large images**: `bagheerasearch "width > 1920" AND "height > 1080"`
- **Find specific ratings**: `bagheerasearch rating = 5`
- **Property-to-Property comparison**: `bagheerasearch --type image HAVING "width > height"` (finds landscape images).

---

## 4. Advanced Date Parsing

One of **Bagheera's** standout features is its **English Natural Language Date Parser**, which allows you to filter files by their modification date using human-readable strings.

### Supported Expressions

- `MODIFIED TODAY`: Files changed since midnight.
- `MODIFIED YESTERDAY`: Files changed during the previous day.
- `MODIFIED LAST [N] DAYS`: Files changed within the last N days (e.g., `MODIFIED LAST 7 DAYS`).
- `MODIFIED [N] YEAR AGO`: Files modified during that specific calendar year.
- **Number Conversion**: You can use words from ONE to TWENTY instead of digits (e.g., `MODIFIED LAST TWO DAYS`).

---

## 5. Tag Management

**Bagheera** handles tags with high precision, including the hierarchical tags often used in KDE/Dolphin.

### Hierarchical Tags

Tags are stored with a path-like structure (e.g., `Person/Julia`).

- **Searching**: Use `tags=Julia` to find anything tagged with "Julia" regardless of the parent category.
- **Explicit Matching**: Use `tags="Person/Julia"` for exact path matches.

### Known Behaviors & Tips

- **Space Handling**: To search for tags containing spaces (e.g., "María Callas"), you must use `tags=María_Callas` or search for the individual parts: `tags:Maria AND tags:Callas`. This is because the **Baloo engine** does not support spaces within the tag search.
- **Normalization**:  Both **Baloo** and **Bagheera** automatically handle accents and diacritics. Searching for `tags:vacacion` will match "Vacación".

---

## 6. Supported types

The following types, to use in `--type` option or `type` property, are supported:

* Archive
* Folder
* Audio
* Video
* Image
* Document
  * Spreadsheet
  * Presentation
* Text

---

## 7. Supported searchable properties

Properties are grouped by file type for easier reference.

### All Files
* filename
* mimetype (Note: You cannot search for full strings like `"text/plain"`. Search for individual words: `mimetype:text AND mimetype:plain`)
* modified (Formatted as yyyy-MM-dd. Note: use always '==' instead of '=' to avoid hour/minute/seconds comparison)
* rating
* tags
* type
* userComment (Note: Search for individual words: `userComment:ready AND userComment:script` because **Baloo engine** does not support quoted strings within the `userComment` search)

### Audio
* Album
* AlbumArtist
* Artist
* BitRate
* Channels
* Comment
* Composer
* Duration (Value in seconds; e.g., `'duration > 300'` for files longer than 5 minutes)
* Genre
* Lyricist
* ReleaseYear
* SampleRate
* TrackNumber

### Documents
* Author
* Copyright
* CreationDate (Formatted as yyyy-MM-dd. Note: inconsistent in **Baloo** with '==' comparison; use only in `having` options to obtain reliable results).
* Generator
* Keywords
* Language
* LineCount
* PageCount
* Publisher
* Subject
* Title
* WordCount

### Media
* AspectRatio
* FrameRate
* Height
* Width

### Images
* ImageDateTime (Formatted as yyyy-MM-dd. Note: inconsistent in **Baloo** with '==' comparison; use only in `having` options to obtain reliable results).
* ImageMake
* ImageModel
* ImageOrientation
* PhotoApertureValue
* PhotoDateTimeOriginal
* PhotoExposureBiasValue
* PhotoExposureTime
* PhotoFlash
* PhotoFNumber
* PhotoFocalLength
* PhotoFocalLengthIn35mmFilm
* PhotoGpsAltitude
* PhotoGpsLatitude
* PhotoGpsLongitude
* PhotoISOSpeedRatings
* PhotoMeteringMode
* PhotoPixelXDimension
* PhotoPixelYDimension
* PhotoSaturation
* PhotoSharpness
* PhotoWhiteBalance

### Other available properties

The following properties are undocumented but available in the source code. They may or may not work, but are worth trying:

* AssistiveAlternateDescription
* Arranger
* AudioCodec
* ColorSpace
* Compilation
* Conductor
* Description
* DiscNumber
* Ensemble
* Label
* License
* Location
* Lyrics
* Manufacturer
* Model
* Opus
* OriginUrl
* OriginEmailSubject
* OriginEmailSender
* OriginEmailMessageId
* Performer
* PixelFormat
* ReplayGainAlbumPeak
* ReplayGainAlbumGain
* ReplayGainTrackPeak
* ReplayGainTrackGain
* TranslationUnitsTotal
* TranslationUnitsWithTranslation
* TranslationUnitsWithDraftTranslation
* TranslationLastAuthor
* TranslationLastUpDate
* TranslationTemplateDate
* VideoCodec

---

## 8. Having

The `HAVING` clause allows you to filter the results returned by **Baloo**. It supports the standard **Baloo** syntax plus the `NOT` operator. Quote or escape shell operators like `>`, `>=`, `<` or `<=`.

Additionally, you can use:

- `==` (case-sensitive equal, behavior is not the same as '==' in Baloo)
- `!=` (not equal)
- `!:` (does not contain)
- Property-to-property comparison (e.g., `width > height`).
- `created`: A **Bagheera-specific** property for file creation dates (Formatted as `yyyy-MM-dd`).

### Important Remarks:

- **Case Sensitivity**: All text comparisons are case-insensitive unless `==` is used.
- **Empty Values**: You can check for the presence or absence of values using empty quotes. For example, `tags!=""` matches any file with at least one tag, while `tags=""` matches files with no tags.
- **Tag Levels**: Comparisons are performed against the full tag path and each individual level. A file tagged `Person/María Callas` matches `Maria`, `María`, `Callas`, `Person`, and the full string.
- **Character Limit**: Unlike **Baloo**, the 3-character minimum limit for string values is not enforced within `having` options.
- **Unicode characters**: If the query contains Unicode characters, double quotes are required. For example, if your tag is `María` or `マリア`, you must write `HAVING 'tags="マリア" tags="María"'` or the query will not return any results.

---

## 9. Subqueries

The main query selects folders; each `SUBQUERY` searches inside those folders.
The global directory restricts the main query, while `--type` filters the
subquery results. Date filters apply to both. The first subquery starts the
result set: a preceding `AND`, `OR` or `OR EXCLUSIVE` is ignored, but `NOT`
complements its results. Subsequent results are combined by file ID:

For a `--type` other than `Folder`, directories are excluded even if Baloo's
index incorrectly classifies them as that type.

- `SUBQUERY` or `AND SUBQUERY`: intersection.
- `AND NOT SUBQUERY`: difference.
- `OR SUBQUERY`: union.
- `OR NOT SUBQUERY`: union with the complement of the subquery.
- `OR EXCLUSIVE SUBQUERY`: symmetric difference (XOR).

The complement consists of indexed items in the selected folders that meet the
subquery type and date filters and are absent from that subquery's filtered
results. If the main query selects no folders, the result is empty.
`AND` and `AND NOT` have precedence over `OR EXCLUSIVE`, which has precedence
over `OR` and `OR NOT`. Operators at the same precedence are evaluated left to
right. Each search can have its own `HAVING`. Results retain the order of their
first appearance in the searches; `--offset` and `--limit` apply after the set
operations. The ordering requested by `--sort` applies separately to each search,
not globally to the combined result.

**Example:** Find documents modified last week inside folders matching "Project".

```bash
bagheerasearch --type Document Project AND SUBQUERY "MODIFIED LAST WEEK"
```

---

## 10. Examples

Here are some practical examples of how to use **Bagheera Search** effectively:

```bash
# Images taken today.
bagheerasearch --type image MODIFIED TODAY

# Landscape is not tagged as "Work".
bagheerasearch --type image HAVING "width > height AND NOT tags:Work"

# Find high-rated files one year ago.
bagheerasearch "rating >= 9 AND MODIFIED 1 YEAR AGO"

# Complex multi-criteria search.
bagheerasearch "(tags:cosplay OR tags:portrait) AND width < 1000 AND rating > 0"

# Get files matching Baloo inside folders matching KDE in "~/Documents".
bagheerasearch --directory '~/Documents' KDE SUBQUERY Baloo

# Get presentations matching Baloo or Bagheera inside folders matching KDE.
bagheerasearch --directory '~/Documents' KDE SUBQUERY Baloo OR SUBQUERY Bagheera --type Presentation

# Get files tagged as "Science" ignoring "Science Fiction" tag.
bagheerasearch tags=Science HAVING "NOT tags=Fiction"
```

---

## 11. Troubleshooting

### Incorrect or missing results

Ensure **Baloo** is enabled and has finished indexing, use `balooctl status` or `balooctl6 status` and check that `Indexer state` is `Idle`. Bagheera reads the Baloo database located at `~/.local/share/baloo/index`.

### Dependency Issues

Bagheera requires the compiled C++ wrapper `libbaloo_wrapper.so`. If the tool fails to start, ensure you have the `KF6Baloo` and `Qt6Core` development headers installed and reinstall the package to trigger the `setup.py` compilation.

