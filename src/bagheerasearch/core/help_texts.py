# flake8: noqa: E501
"""
Help texts and documentation strings for Bagheera Search Tool.
This module facilitates future localization (i18n).
"""
import os

# Default language for configuration
DEFAULT_LANGUAGE = "en"

_HELP_TEXTS = {
    "en": {
        "CLI_DESC": "An improved search tool for Baloo",
        "ARG_QUERY": "list of words to query for",
        "ARG_DIR": "limit search to specified directory tree",
        "ARG_HAVING": "having expression applied over query results",
        "ARG_ID": "show document IDs",
        "ARG_KONSOLE": "show files using file:/ and quotes",
        "ARG_LIMIT": "the maximum number of results",
        "ARG_OFFSET": "offset from which to start the search",
        "ARG_SUBQUERY": "enable a subquery over folder results with or without a query",
        "ARG_SUBQUERY_INDENT": "subquery results indent character",
        "ARG_SUBQUERY_HAVING": "having expression applied over subquery results",
        "ARG_SORT": "sorting criteria <auto|none>",
        "ARG_TYPE": "type of Baloo data to be searched",
        "ARG_VERBOSE": "Verbose mode",
        "ARG_DAY": "day fixed filter, --month is required",
        "ARG_MONTH": "month fixed filter, --year is required",
        "ARG_YEAR": "year fixed filter",
        "ARG_HELP_QUERY": "show query syntax help",
        "ARG_VERSION": "show version information",
        "ERR_LOAD_CONFIG": "Warning: Could not load config file: {}",
        "ERR_SAVE_CONFIG": "Warning: Could not save config file: {}",
        "COPYRIGHT_INFO": "Copyright (C) {year} by {author} and, mostly, the good people at KDE",
        "ERR_MISSING_MONTH": "Missing --month (required when --day is used)",
        "ERR_MISSING_YEAR": "Missing --year (required when --month is used)",
        "MSG_QUERY": "Query: '{}'",
        "MSG_MAIN_OPTS": "Main Options: {}",
        "MSG_OTHER_OPTS": "Other Options: {}",
        "MSG_ID_INFO": " [ID: {}]",
        "MSG_NO_RESULTS": "No results found.",
        "MSG_TOTAL_RESULTS": "Total: {} files found in {:.2f} seconds.",
        "MSG_CANCELED": "\nSearch canceled at user request.",
        "ERR_EXEC_SEARCH": "Error executing search: {}",
        "ERR_CRITICAL": "Critical error: {}",
        "HELP_QUERY_TEMPLATE": """{prog_name} uses the Baloo search engine, which is part of the KDE ecosystem. The following help section is derived from Baloo documentation (as of 2025-01-01) with additional Bagheera-specific details. It may not reflect the latest Baloo features; please refer to official Baloo resources for the most up-to-date information.

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
  · mimetype (Note: You cannot search for full strings like "text/plain". Search for individual words: 'mimetype:text AND mimetype:plain')
  · modified (Formatted as yyyy-MM-dd)
  · rating
  · tags
  · userComment (Note: Search for individual words: 'userComment:ready AND userComment:script' because Baloo engine does not support quoted strings within the 'userComment' search)

Audio
  · Album
  · AlbumArtist
  · Artist
  · BitRate
  · Channels
  · Comment
  · Composer
  · Duration (Value in seconds; e.g., 'duration > 300' for files longer than 5 minutes)
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
  · ImageDateTime (Formatted as yyyy-MM-dd. Note: Currently inconsistent in Baloo; use in 'having' options for reliability).
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

The '--having' and '--subquery-having' options allow you to filter the results returned by Baloo. They support the standard Baloo syntax plus the 'NOT' operator.

Additionally, you can use:

- '==' (case-sensitive equal)
- '!=' (not equal)
- '!:' (does not contains)
- Property-to-property comparison (e.g., 'width > height').
- 'created', a Bagheera-specific property for file creation dates (Formatted as 'yyyy-MM-dd').

Important Remarks:
· Case Sensitivity: All text comparisons are case-insensitive unless '==' is used.
· Empty Values: You can check for the presence or absence of values using empty quotes. For example, 'tags!=""' matches any file with at least one tag, while 'tags=""' matches files with no tags.
· Tag Levels: Comparisons are performed against the full tag path and each individual level. A file tagged 'Person/Maria Callas' matches 'Maria', 'Callas', 'Person', and the full string.
· Character Limit: Unlike Baloo, the 3-character minimum limit for string values is not enforced within 'having' options.

Having exclusion example:
Get files tagget as "Science" ignoring "Science Fiction" tag.

    {prog_id} tags=Science --having "NOT tags=Fiction" """
    },
    "es": {
        "CLI_DESC": "Una herramienta de búsqueda mejorada para Baloo",
        "ARG_QUERY": "lista de palabras para buscar",
        "ARG_DIR": "limitar la búsqueda al árbol de directorios especificado",
        "ARG_HAVING": "expresión 'having' aplicada sobre los resultados de la consulta",
        "ARG_ID": "mostrar los IDs de los documentos",
        "ARG_KONSOLE": "mostrar archivos usando file:/ y comillas",
        "ARG_LIMIT": "el número máximo de resultados",
        "ARG_OFFSET": "desplazamiento desde el cual iniciar la búsqueda",
        "ARG_SUBQUERY": "habilitar una subconsulta sobre los resultados de carpetas con o sin consulta",
        "ARG_SUBQUERY_INDENT": "carácter de indentación para los resultados de la subconsulta",
        "ARG_SUBQUERY_HAVING": "expresión 'having' aplicada sobre los resultados de la subconsulta",
        "ARG_SORT": "criterio de ordenación <auto|none>",
        "ARG_TYPE": "tipo de datos Baloo a buscar",
        "ARG_VERBOSE": "Modo detallado",
        "ARG_DAY": "filtro fijo de día, se requiere --month",
        "ARG_MONTH": "filtro fijo de mes, se requiere --year",
        "ARG_YEAR": "filtro fijo de año",
        "ARG_HELP_QUERY": "mostrar ayuda de sintaxis de consulta",
        "ARG_VERSION": "mostrar información de la versión",
        "ERR_LOAD_CONFIG": "Advertencia: No se pudo cargar el archivo de configuración: {}",
        "ERR_SAVE_CONFIG": "Advertencia: No se pudo guardar el archivo de configuración: {}",
        "COPYRIGHT_INFO": "Copyright (C) {year} por {author} y, mayormente, la buena gente de KDE",
        "ERR_MISSING_MONTH": "Falta --month (requerido cuando se usa --day)",
        "ERR_MISSING_YEAR": "Falta --year (requerido cuando se usa --month)",
        "MSG_QUERY": "Consulta: '{}'",
        "MSG_MAIN_OPTS": "Opciones principales: {}",
        "MSG_OTHER_OPTS": "Otras opciones: {}",
        "MSG_ID_INFO": " [ID: {}]",
        "MSG_NO_RESULTS": "No se encontraron resultados.",
        "MSG_TOTAL_RESULTS": "Total: {} archivos encontrados en {:.2f} segundos.",
        "MSG_CANCELED": "\nBúsqueda cancelada a petición del usuario.",
        "ERR_EXEC_SEARCH": "Error ejecutando la búsqueda: {}",
        "ERR_CRITICAL": "Error crítico: {}",
        "HELP_QUERY_TEMPLATE": """{prog_name} utiliza el motor de búsqueda Baloo, que forma parte del ecosistema KDE. La siguiente sección de ayuda se deriva de la documentación de Baloo (a fecha 01/01/2025) con detalles adicionales específicos de Bagheera. Es posible que no refleje las últimas características de Baloo; por favor, consulte los recursos oficiales de Baloo para obtener la información más actualizada.

Baloo ofrece una sintaxis rica para buscar a través de sus archivos. Se pueden buscar ciertas propiedades de un archivo.

Por ejemplo, 'type' puede usarse para filtrar archivos según su tipo general:

  type:Audio OR type:Document

Se admiten los siguientes operadores de comparación, pero tenga en cuenta que el operador 'no es igual' (!=) no está disponible en el motor de búsqueda de Baloo.
  · :   - contiene (solo para comparación de texto)
  · =   - igual
  · >   - mayor que
  · >=  - mayor que o igual a
  · <   - menor que
  · <=  - menor que o igual a

Actualmente se admiten los siguientes tipos, para usar en la propiedad --type:
  · Archive
  · Folder
  · Audio
  · Video
  · Image
  · Document
    · Spreadsheet
    · Presentation
  · Text

Estas expresiones pueden combinarse mediante los operadores lógicos 'AND' u 'OR' y paréntesis adicionales, pero tenga en cuenta que el operador lógico 'NOT' no está disponible.


- PROPIEDADES BUSCABLES -

La lista completa de propiedades que se pueden usar en las búsquedas se enumera a continuación, estas están agrupadas por tipo de archivo.

Todos los archivos
  · filename
  · mimetype (Nota: No se pueden buscar cadenas completas como "text/plain". Busque palabras individuales: 'mimetype:text AND mimetype:plain')
  · modified (Formateado como aaaa-MM-dd)
  · rating
  · tags
  · userComment (Nota: Busque palabras individuales: 'userComment:ready AND userComment:script' porque el motor de búsqueda de Baloo no admite cadenas entrecomilladas dentro de la búsqueda 'userComment')

Audio
  · Album
  · AlbumArtist
  · Artist
  · BitRate
  · Channels
  · Comment
  · Composer
  · Duration (Valor en segundos; p. ej., 'duration > 300' para archivos de más de 5 minutos)
  · Genre
  · Lyricist
  · ReleaseYear
  · SampleRate
  · TrackNumber

Documentos
  · Author
  · Copyright
  · CreationDate (Formateado como aaaa-MM-dd)
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

Imágenes
  · ImageDateTime (Formateado como aaaa-MM-dd. Nota: Actualmente inconsistente en Baloo, pero se puede usar con las opciones 'having').
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

Las siguientes propiedades no están documentadas pero están disponibles en el código fuente. Pueden funcionar o no, pero vale la pena intentarlo:
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

La documentación de Baloo termina aquí, pero {prog_name} añade algunas características adicionales.


- CARACTERÍSTICAS ESPECÍFICAS DE BAGHEERA -

El motor de búsqueda reconoce ciertas frases en lenguaje natural en inglés, siempre que estén en mayúsculas, y las transforma en consultas interpretables.

Los patrones de lenguaje natural admitidos son:
  · MODIFIED TODAY
  · MODIFIED YESTERDAY
  · MODIFIED THIS [ DAY | WEEK | MONTH | YEAR ]
  · MODIFIED LAST <NUMBER> [ DAYS | WEEKS | MONTHS | YEARS ]
  · MODIFIED <NUMBER> [ DAYS | WEEKS | MONTHS | YEARS ] AGO

<NUMBER> puede ser cualquier número o el texto de un número del ONE al TWENTY (en inglés).

- Opción 'Subquery' -

La opción '--subquery' le permite realizar una búsqueda secundaria dentro de las carpetas obtenidas de la consulta principal. Esto es particularmente útil para refinar búsquedas dentro de carpetas específicas. Al usar '--subquery', la consulta principal primero filtra las carpetas según los criterios iniciales; luego, la subconsulta se aplica a todos los archivos ubicados dentro de esas carpetas para afinar aún más la búsqueda.
Puede proporcionar una cadena de consulta con la opción '--subquery' para filtrar los resultados de la consulta principal, o puede usar la opción sin texto adicional para simplemente se muestren todos los elementos obtenidos.
Este comportamiento es útil para realizar búsquedas profundas. Por ejemplo, puede buscar todas las carpetas que contengan 'Proyecto' en su nombre y luego usar una subconsulta para encontrar documentos dentro de esas carpetas que fueron modificados en la última semana.

Ejemplo:
Esta es una consulta compleja para localizar todos los archivos del tipo 'Presentation' situados dentro de cualquier directorio que contenga 'KDE' en su nombre, específicamente bajo la ruta '~/Documents'. La búsqueda se refina aún más para incluir solo aquellos archivos que contengan 'Baloo' o 'Bagheera' en sus metadatos o nombre de archivo y que no estén etiquetados como 'Obsolete' o 'Revised'.

    {prog_id} --directory '~/Documents' KDE --subquery 'Baloo OR Bagheera' --type Presentation --having 'NOT (tags=Obsolete OR tags=Revised)'


- Opciones '--having' y '--subquery-having' -

Las opciones '--having' y '--subquery-having' le permiten filtrar los resultados devueltos por Baloo. Admiten la sintaxis estándar de Baloo y además el operador 'NOT'.

Aparte, puede usar para comparar los siguientes operadores:

- '==' (igual sensible a mayúsculas/minúsculas)
- '!=' (no es igual)
- '!:' (no contiene)
- Comparación de propiedad a propiedad (p. ej., 'width > height').
- 'created', una propiedad específica de Bagheera para fechas de creación de archivos (Formateado como 'aaaa-MM-dd').

Observaciones importantes:
· Sensibilidad a mayúsculas: Todas las comparaciones de texto son insensibles a mayúsculas a menos que se use '=='.
· Valores vacíos: Puede verificar la presencia o ausencia de valores usando comillas vacías. Por ejemplo, 'tags!=""' coincide con cualquier archivo con al menos una etiqueta, mientras que 'tags=""' coincide con archivos sin etiquetas.
· Niveles de etiquetas: Las comparaciones se realizan contra la ruta completa de la etiqueta y cada nivel individual. Un archivo etiquetado como 'Persona/Maria Callas' coincide con 'Maria', 'Callas', 'Persona' y la cadena completa.
· Límite de caracteres: A diferencia de Baloo, el límite mínimo de 3 caracteres para valores de cadena no se aplica dentro de las opciones 'having'.

Ejemplo de exclusión con Having:
Obtener archivos etiquetados como "Ciencia" ignorando la etiqueta "Ciencia Ficción".

    {prog_id} tags=Ciencia --having "NOT tags=Ficción" """
    },
    "gl": {
        "CLI_DESC": "Unha ferramenta de busca mellorada para Baloo",
        "ARG_QUERY": "lista de palabras para buscar",
        "ARG_DIR": "limitar a busca á árbore de directorios especificada",
        "ARG_HAVING": "expresión 'having' aplicada sobre os resultados da consulta",
        "ARG_ID": "amosar os IDs dos documentos",
        "ARG_KONSOLE": "amosar ficheiros usando file:/ e comiñas",
        "ARG_LIMIT": "o número máximo de resultados",
        "ARG_OFFSET": "desprazamento desde o que iniciar a busca",
        "ARG_SUBQUERY": "habilitar unha subconsulta sobre os resultados de cartafoles con ou sen consulta",
        "ARG_SUBQUERY_INDENT": "carácter de indentación para os resultados da subconsulta",
        "ARG_SUBQUERY_HAVING": "expresión 'having' aplicada sobre os resultados da subconsulta",
        "ARG_SORT": "criterio de ordenación <auto|none>",
        "ARG_TYPE": "tipo de datos Baloo para buscar",
        "ARG_VERBOSE": "Modo detallado",
        "ARG_DAY": "filtro fixo de día, requírese --month",
        "ARG_MONTH": "filtro fixo de mes, requírese --year",
        "ARG_YEAR": "filtro fixo de ano",
        "ARG_HELP_QUERY": "amosar axuda de sintaxe de consulta",
        "ARG_VERSION": "amosar información da versión",
        "ERR_LOAD_CONFIG": "Advertencia: Non se puido cargar o ficheiro de configuración: {}",
        "ERR_SAVE_CONFIG": "Advertencia: Non se puido gardar o ficheiro de configuración: {}",
        "COPYRIGHT_INFO": "Copyright (C) {year} por {author} e, maiormente, a boa xente de KDE",
        "ERR_MISSING_MONTH": "Falta --month (requirido cando se usa --day)",
        "ERR_MISSING_YEAR": "Falta --year (requirido cando se usa --month)",
        "MSG_QUERY": "Consulta: '{}'",
        "MSG_MAIN_OPTS": "Opcións principais: {}",
        "MSG_OTHER_OPTS": "Outras opcións: {}",
        "MSG_ID_INFO": " [ID: {}]",
        "MSG_NO_RESULTS": "Non se atoparon resultados.",
        "MSG_TOTAL_RESULTS": "Total: {} ficheiros atopados en {:.2f} segundos.",
        "MSG_CANCELED": "\nBusca cancelada a petición do usuario.",
        "ERR_EXEC_SEARCH": "Erro executando a busca: {}",
        "ERR_CRITICAL": "Erro crítico: {}",
        "HELP_QUERY_TEMPLATE": """{prog_name} utiliza o motor de busca Baloo, que forma parte do ecosistema KDE. A seguinte sección de axuda deriva da documentación de Baloo (a data 01/01/2025) con detalles adicionais específicos de Bagheera. É posible que non reflexe as últimas características de Baloo; por favor, consulte os recursos oficiais de Baloo para obter a información máis actualizada.

Baloo ofrece unha sintaxe rica para buscar a través dos seus ficheiros. Pódense buscar certas propiedades dun ficheiro.

Por exemplo, 'type' pode usarse para filtrar ficheiros segundo o seu tipo xeral:

  type:Audio OR type:Document

Admítense os seguintes operadores de comparación, pero teña en conta que o operador 'non é igual' (!=) non está dispoñible no motor de busca de Baloo.
  · :   - contén (só para comparación de texto)
  · =   - igual
  · >   - maior que
  · >=  - maior que ou igual a
  · <   - menor que
  · <=  - menor que ou igual a

Actualmente admítense os seguintes tipos, para usar na propiedade --type:
  · Archive
  · Folder
  · Audio
  · Video
  · Image
  · Document
    · Spreadsheet
    · Presentation
  · Text

Estas expresións poden combinarse mediante os operadores lóxicos 'AND' ou 'OR' e parénteses adicionais, pero teña en conta que o operador lóxico 'NOT' non está dispoñible.


- PROPIEDADES BUSCABLES -

A lista completa de propiedades que se poden usar nas buscas enumérase a continuación, estas están agrupadas por tipo de ficheiro.

Todos os ficheiros
  · filename
  · mimetype (Nota: Non se poden buscar cadeas completas como "text/plain". Busque palabras individuais: 'mimetype:text AND mimetype:plain')
  · modified (Formatado como aaaa-MM-dd)
  · rating
  · tags
  · userComment (Nota: Busque palabras individuais: 'userComment:ready AND userComment:script' porque o motor de busca de Baloo non admite cadeas entrecomilladas dentro da busca 'userComment')

Audio
  · Album
  · AlbumArtist
  · Artist
  · BitRate
  · Channels
  · Comment
  · Composer
  · Duration (Valor en segundos; p. ex., 'duration > 300' para ficheiros de máis de 5 minutos)
  · Genre
  · Lyricist
  · ReleaseYear
  · SampleRate
  · TrackNumber

Documentos
  · Author
  · Copyright
  · CreationDate (Formatado como aaaa-MM-dd)
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

Imaxes
  · ImageDateTime (Formatado como aaaa-MM-dd. Nota: Actualmente inconsistente en Baloo, pero pódese usar coas opcións 'having').
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

As seguintes propiedades non están documentadas pero están dispoñibles no código fonte. Poden funcionar ou non, pero vale a pena tentalo:
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

A documentación de Baloo remata aquí, pero {prog_name} engade algunhas características adicionais.


- CARACTERÍSTICAS ESPECÍFICAS DE BAGHEERA -

O motor de busca recoñece certas frases en linguaxe natural en inglés, sempre que estean en maiúsculas, e transfórmaas en consultas interpretables.

Os patróns de linguaxe natural admitidos son:
  · MODIFIED TODAY
  · MODIFIED YESTERDAY
  · MODIFIED THIS [ DAY | WEEK | MONTH | YEAR ]
  · MODIFIED LAST <NUMBER> [ DAYS | WEEKS | MONTHS | YEARS ]
  · MODIFIED <NUMBER> [ DAYS | WEEKS | MONTHS | YEARS ] AGO

<NUMBER> pode ser calquera número ou o texto dun número do ONE ao TWENTY (en inglés).

- Opción 'Subquery' -

A opción '--subquery' permítelle realizar unha busca secundaria dentro dos cartafoles obtidos da consulta principal. Isto é particularmente útil para refinar buscas dentro de cartafoles específicos. Ao usar '--subquery', a consulta principal primeiro filtra os cartafoles segundo os criterios iniciais; logo, a subconsulta aplícase a todos os ficheiros situados dentro deses cartafoles para afinar aínda máis a busca.
Pode proporcionar unha cadea de consulta coa opción '--subquery' para filtrar os resultados da consulta principal, ou pode usar a opción sen texto adicional para que simplemente se amosen todos os elementos obtidos.
Este comportamento é útil para realizar buscas profundas. Por exemplo, pode buscar todos os cartafoles que conteñan 'Proxecto' no seu nome e logo usar unha subconsulta para atopar documentos dentro deses cartafoles que foron modificados na última semana.

Exemplo:
Esta é unha consulta complexa para localizar todos os ficheiros do tipo 'Presentation' situados dentro de calquera directorio que conteña 'KDE' no seu nome, especificamente baixo a ruta '~/Documents'. A busca refínase aínda máis para incluír só aqueles ficheiros que conteñan 'Baloo' ou 'Bagheera' nos seus metadatos ou nome de ficheiro e que non estean etiquetados como 'Obsolete' ou 'Revised'.

    {prog_id} --directory '~/Documents' KDE --subquery 'Baloo OR Bagheera' --type Presentation --having 'NOT (tags=Obsolete OR tags=Revised)'


- Opcións '--having' e '--subquery-having' -

As opcións '--having' e '--subquery-having' permítenlle filtrar os resultados devoltos por Baloo. Admiten a sintaxis estándar de Baloo e ademais o operador 'NOT'.

Aparte, pode usar para comparar os seguintes operadores:

- '==' (igual sensible a maiúsculas/minúsculas)
- '!=' (non é igual)
- '!:' (non contén)
- Comparación de propiedade a propiedade (p. ex., 'width > height').
- 'created', unha propiedade específica de Bagheera para datas de creación de ficheiros (Formatado como 'aaaa-MM-dd').

Observacións importantes:
· Sensibilidade a maiúsculas: Todas as comparacións de texto son insensibles a maiúsculas a menos que se use '=='.
· Valores baleiros: Pode verificar a presenza ou ausencia de valores usando comiñas baleiras. Por exemplo, 'tags!=""' coincide con calquera ficheiro con polo menos unha etiqueta, mentres que 'tags=""' coincide con ficheiros sen etiquetas.
· Niveis de etiquetas: As comparacións realízanse contra a ruta completa da etiqueta e cada nivel individual. Un ficheiro etiquetado como 'Persoa/Maria Callas' coincide con 'Maria', 'Callas', 'Persoa' e a cadea completa.
· Límite de caracteres: A diferenza de Baloo, o límite mínimo de 3 caracteres para valores de cadea non se aplica dentro das opcións 'having'.

Exemplo de exclusión con Having:
Obter ficheiros etiquetados como "Ciencia" ignorando a etiqueta "Ciencia Ficción".

    {prog_id} tags=Ciencia --having "NOT tags=Ficción" """
    }
}


def _get_current_language():
    """Determines the language to use for help strings based on environment."""
    lang = os.getenv("BAGHEERA_LANG")

    if not lang:
        sys_lang = os.getenv("LANG")
        if sys_lang:
            lang = sys_lang[0:2].lower()
        else:
            lang = DEFAULT_LANGUAGE

    return lang if lang in _HELP_TEXTS else DEFAULT_LANGUAGE


CURRENT_LANGUAGE = _get_current_language()


class _HelpTextsProxy:
    """
    A proxy class to access help strings from the _HELP_TEXTS dictionary.
    """
    def __getattr__(self, name):
        lang_texts = _HELP_TEXTS.get(CURRENT_LANGUAGE, _HELP_TEXTS[DEFAULT_LANGUAGE])
        text = lang_texts.get(name)
        if text is None:
            text = _HELP_TEXTS[DEFAULT_LANGUAGE].get(name, f"_{name}_")
        return text


HelpTexts = _HelpTextsProxy()
