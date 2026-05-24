"""
Help texts and documentation strings for Bagheera Search Tool.
This module facilitates future localization (i18n).
"""

HELP_QUERY_TEMPLATE = """{prog_name} uses the Baloo search engine, which is part of the KDE ecosystem. The following help section is derived from Baloo documentation (as of 2025-01-01) with additional Bagheera-specific details. It may not reflect the latest Baloo features; please refer to official Baloo resources for the most up-to-date information.

Baloo offers a rich syntax for searching through your files. Certain attributes of a file can be searched through.

For example 'type' can be used to filter for files based on their general type:

  type:Audio OR type:Document

The following comparison operators are supported, but note that 'not equal' (!=) operator is not available in Baloo search engine.
  · :   - contains (only for text comparison)
  · =   - equal
  · >   - greater than
  · >=  - greater than or equal to
  · <   - less than
  · <=  - less than or equal to

Currently the following types, to use in --type property, are supported:
  · Archive
  · Folder
  · Audio
  · Video
  · Image
  · Document
    · Spreadsheet
    · Presentation
  · Text

These expressions can be combined using logical operators 'AND' or 'OR' and additional parenthesis, but note that 'NOT' logical operator is not available.


- SEARCHABLE PROPERTIES -

The full list of searchable properties is listed below, grouped by file type.

All Files
  · filename
  · mimetype (Note: You cannot search for full strings like `"text/plain"`. Search for individual words: `mimetype:text AND mimetype:plain`)
  · modified (Formatted as yyyy-MM-dd)
  · rating
  · tags
  · userComment (Note: Search for individual words: `userComment:ready AND userComment:script` because **Baloo engine** does not support quoted strings within the `userComment` search)

Audio
  · Album
  · AlbumArtist
  · Artist
  · BitRate
  · Channels
  · Comment
  · Composer
  · Duration (Value in seconds; e.g., `'duration > 300'` for files longer than 5 minutes)
  · Genre
  · Lyricist
  · ReleaseYear
  · SampleRate
  · TrackNumber

Documents
  · Author
  · Copyright
  · CreationDate (Formatted as yyyy-MM-dd)
  · Generator
  · Keywords
  · Language
  · LineCount
  · PageCount
  · Publisher
  · Subject
  · Title
  · WordCount

Media
  · AspectRatio
  · FrameRate
  · Height
  · Width

Images
  · ImageDateTime (Formatted as yyyy-MM-dd. Note: Currently inconsistent in **Baloo**; use in `having` options for reliability).
  · ImageMake
  · ImageModel
  · ImageOrientation
  · PhotoApertureValue
  · PhotoDateTimeOriginal
  · PhotoExposureBiasValue
  · PhotoExposureTime
  · PhotoFlash
  · PhotoFNumber
  · PhotoFocalLength
  · PhotoFocalLengthIn35mmFilm
  · PhotoGpsAltitude
  · PhotoGpsLatitude
  · PhotoGpsLongitude
  · PhotoISOSpeedRatings
  · PhotoMeteringMode
  · PhotoPixelXDimension
  · PhotoPixelYDimension
  · PhotoSaturation
  · PhotoSharpness
  · PhotoWhiteBalance

The following properties are undocumented but available in the source code. They may or may not work, but are worth trying:
  · AssistiveAlternateDescription
  · Arranger
  · AudioCodec
  · ColorSpace
  · Compilation
  · Conductor
  · Description
  · DiscNumber
  · Ensemble
  · Label
  · License
  · Location
  · Lyrics
  · Manufacturer
  · Model
  · Opus
  · OriginUrl
  · OriginEmailSubject
  · OriginEmailSender
  · OriginEmailMessageId
  · Performer
  · PixelFormat
  · ReplayGainAlbumPeak
  · ReplayGainAlbumGain
  · ReplayGainTrackPeak
  · ReplayGainTrackGain
  · TranslationUnitsTotal
  · TranslationUnitsWithTranslation
  · TranslationUnitsWithDraftTranslation
  · TranslationLastAuthor
  · TranslationLastUpDate
  · TranslationTemplateDate
  · VideoCodec

Baloo documentation ends here, but {prog_name} adds some extra features on top of it.


- BAGHEERA-SPECIFIC FEATURES -

The search engine recognizes certain English natural language phrases, provided they are capitalized, and transforms them into interpretable queries.

Supported natural language patterns are:
  · MODIFIED TODAY
  · MODIFIED YESTERDAY
  · MODIFIED THIS [ DAY | WEEK | MONTH | YEAR ]
  · MODIFIED LAST <NUMBER> [ DAYS | WEEKS | MONTHS | YEARS ]
  · MODIFIED <NUMBER> [ DAYS | WEEKS | MONTHS | YEARS ] AGO

<NUMBER> can be any number or a number text from ONE to TWENTY.

- 'Subquery' option -

The '--subquery' option allows you to perform a secondary search within the folders obtained from main query. This is particularly useful for refining searches within specific folders. When using '--subquery', the main query first filters folders based on the initial criteria; the subquery is then applied to all files located within those folders to further narrow down the search.
You can provide a query string with the '--subquery' option to filter the results of the main query, or you can use the option without additional text to simply list all items within those results.
This behavior is useful for performing deep searches. For example, you can search for all folders with 'Project' in their name and then use a subquery to find documents within those folders that were modified in the last week.

Example:
This is a complex query to locate all files of the 'Presentation' type situated within any directory that contains 'KDE' in its name, specifically under the '~/Documents' path. The search is further refined to include only those files that contain either 'Baloo' or 'Bagheera' in their metadata or filename and are not tagged as 'Obsolete' or 'Revised'.

    {prog_id} --directory '~/Documents' KDE --subquery 'Baloo OR Bagheera' --type Presentation --having 'NOT (tags=Obsolete OR tags=Revised)'


- 'Having' and 'subquery-having' options -

The '--having' and '--subquery-having' options allow you to filter the results returned by **Baloo**. They support the standard **Baloo** syntax plus the `NOT` operator.

Additionally, you can use:

- '==' (case-sensitive equal)
- '!=' (not equal)
- '!:' (does not contains)
- Property-to-property comparison (e.g., `width > height`).
- 'created', a Bagheera-specific property for file creation dates (Formatted as `yyyy-MM-dd`).

Important Remarks:
· Case Sensitivity: All text comparisons are case-insensitive unless '==' is used.
· Empty Values: You can check for the presence or absence of values using empty quotes. For example, 'tags!=""' matches any file with at least one tag, while 'tags=""' matches files with no tags.
· Tag Levels: Comparisons are performed against the full tag path and each individual level. A file tagged 'Person/Maria Callas' matches 'Maria', 'Callas', 'Person', and the full string.
· Character Limit: Unlike Baloo, the 3-character minimum limit for string values is not enforced within 'having' options.

Having exclusion example:
Get files tagget as "Science" ignoring "Science Fiction" tag.

    {prog_id} tags=Science --having "NOT tags=Fiction" """
