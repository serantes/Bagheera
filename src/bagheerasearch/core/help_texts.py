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
        "ARG_QUERY": "query [HAVING expression] [[operator] SUBQUERY query [HAVING expression]]...",
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
        "ERR_REMOVED_OPTION": "option {} has been removed; use HAVING or SUBQUERY in the query",
        "ERR_UNKNOWN_OPTIONS": "unrecognized arguments: {}",
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
  · :   - contains (only for text comparison) or begin with (for tags)
  · =   - equal
  · ==  - equal for date properties to avoid hour/minute/second comparison
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
  · tags (Note: You cannot search for strings with spaces like "Science Fiction", but you can use underscores instead: 'tags:Science_Fiction')
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
  · CreationDate (Formatted as yyyy-MM-dd. Note: inconsistent in **Baloo** with '==' comparison; use in 'having' options for reliability).)
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
  · ImageDateTime (Formatted as yyyy-MM-dd. Note: inconsistent in **Baloo** with '==' comparison; use in 'having' options for reliability).
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

- SUBQUERY clause -

The main query selects folders. Each SUBQUERY searches independently inside those folders, and --type applies to the items found there. The first SUBQUERY starts the result set: its AND or OR is ignored, but NOT complements its results. Subsequent SUBQUERY or AND SUBQUERY clauses intersect results; AND NOT SUBQUERY subtracts them; OR SUBQUERY unions them; OR NOT SUBQUERY unions them with the complement; OR EXCLUSIVE SUBQUERY computes the symmetric difference (XOR).
The complement is relative to all indexed items in the selected folders matching the subquery type and date filters. AND and AND NOT take precedence over XOR, which takes precedence over OR and OR NOT. Operators at the same precedence are evaluated left to right.
An empty SUBQUERY matches all items in the selected folders. HAVING filters the immediately preceding search; empty HAVING clauses are ignored and repeated HAVING clauses on that search are joined with AND. Clause names and operators must be uppercase. Limit and offset apply after combining results.

Example:
Find presentations in folders matching KDE, containing Baloo or Bagheera and not tagged Obsolete.

    {prog_id} --directory '~/Documents' KDE SUBQUERY Baloo HAVING 'NOT tags=Obsolete' OR SUBQUERY Bagheera HAVING 'NOT tags=Obsolete' --type Presentation


- HAVING clause -

The HAVING clause filters the results returned by Baloo. It supports the standard Baloo syntax plus the 'NOT' operator.

Additionally, you can use:

- '==' (case-sensitive equal with strings), behaviour is not the same as '==' in Baloo)
- '!=' (not equal)
- '!:' (does not contains)
- Property-to-property comparison (e.g., 'width > height').
- 'created', a Bagheera-specific property for file creation dates (Formatted as 'yyyy-MM-dd').

Important Remarks:
· Case Sensitivity: All text comparisons are case-insensitive unless '==' is used.
· Empty Values: You can check for the presence or absence of values using empty quotes. For example, 'tags!=""' matches any file with at least one tag, while 'tags=""' matches files with no tags.
· Tag Levels: Comparisons are performed against the full tag path and each individual level. A file tagged 'Person/María Callas' matches 'Maria', 'Callas', 'Person', and the full string.
· Character Limit: Unlike Baloo, the 3-character minimum limit for string values is not enforced within 'having' options.
· Unicode Characters: If the query contains Unicode characters double quotes are required. For example, if your tag is 富士山, write HAVING 'tags="富士山"' or the query will not return any results.

Having exclusion example:
Get files tagget as "Science" ignoring "Science Fiction" tag.

    {prog_id} tags=Science HAVING "NOT tags=Fiction" """
    },
    "es": {
        "CLI_DESC": "Una herramienta de búsqueda mejorada para Baloo",
        "ARG_QUERY": "consulta [HAVING expresión] [[operador] SUBQUERY consulta [HAVING expresión]]...",
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
        "ERR_REMOVED_OPTION": "la opción {} se ha eliminado; use HAVING o SUBQUERY en la consulta",
        "ERR_UNKNOWN_OPTIONS": "argumentos no reconocidos: {}",
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
  · :   - contiene (solo para comparación de texto) o empieza con (para etiquetas)
  · =   - igual
  · ==  - igual en propiedades de fechas para evitar la comparación de hora/minuto/segundo
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
  · tags (Nota: No se pueden buscar cadenas completas como "Science Fiction", pero la búsqueda con guiones bajos funciona: 'tags:Science_Fiction')
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
  · CreationDate (Formateado como aaaa-MM-dd. Nota: inconsistente en **Baloo** usando el comparador '==', pero se puede usar con las opciones 'having')
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
  · ImageDateTime (Formateado como aaaa-MM-dd. Nota: inconsistente en **Baloo** usando el comparador '==', pero se puede usar con las opciones 'having')
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

- Cláusula SUBQUERY -

La consulta principal selecciona carpetas. Cada SUBQUERY busca independientemente dentro de ellas; --type se aplica a los elementos encontrados. La primera SUBQUERY inicia el conjunto: se ignora su AND u OR, pero se respeta NOT. Las siguientes SUBQUERY o AND SUBQUERY intersectan resultados; AND NOT SUBQUERY los resta; OR SUBQUERY los une; OR NOT SUBQUERY los une con el complemento; OR EXCLUSIVE SUBQUERY calcula la diferencia simétrica (XOR).
El complemento se calcula respecto a los elementos indexados en las carpetas seleccionadas que cumplen los filtros de tipo y fecha de las subconsultas. AND y AND NOT tienen prioridad sobre XOR, que tiene prioridad sobre OR y OR NOT. Los operadores de igual prioridad se evalúan de izquierda a derecha.
Una SUBQUERY vacía coincide con todos los elementos de las carpetas seleccionadas. HAVING filtra la búsqueda inmediatamente anterior; las cláusulas HAVING vacías se ignoran y las repetidas en una búsqueda se unen con AND. Los nombres de cláusulas y operadores deben estar en mayúsculas. El límite y el desplazamiento se aplican después de combinar los resultados.

Ejemplo:
Buscar presentaciones en carpetas que coincidan con KDE, que contengan Baloo o Bagheera y no estén etiquetadas como Obsolete.

    {prog_id} --directory '~/Documents' KDE SUBQUERY Baloo HAVING 'NOT tags=Obsolete' OR SUBQUERY Bagheera HAVING 'NOT tags=Obsolete' --type Presentation


- Cláusula HAVING -

La cláusula HAVING permite filtrar los resultados devueltos por Baloo. Admite la sintaxis estándar de Baloo y además el operador 'NOT'.

Aparte, puede usar para comparar los siguientes operadores:

- '==' (igual sensible a mayúsculas/minúsculas, el comportamiento no es el mismo que '==' en Baloo)
- '!=' (no es igual)
- '!:' (no contiene)
- Comparación de propiedad a propiedad (p. ej., 'width > height').
- 'created', una propiedad específica de Bagheera para fechas de creación de archivos (Formateado como 'aaaa-MM-dd').

Observaciones importantes:
· Sensibilidad a mayúsculas: Todas las comparaciones de texto son insensibles a mayúsculas a menos que se use '=='.
· Valores vacíos: Puede verificar la presencia o ausencia de valores usando comillas vacías. Por ejemplo, 'tags!=""' coincide con cualquier archivo con al menos una etiqueta, mientras que 'tags=""' coincide con archivos sin etiquetas.
· Niveles de etiquetas: Las comparaciones se realizan contra la ruta completa de la etiqueta y cada nivel individual. Un archivo etiquetado como 'Persona/María Callas' coincide con 'Maria', 'Callas', 'Persona' y la cadena completa.
· Límite de caracteres: A diferencia de Baloo, el límite mínimo de 3 caracteres para valores de cadena no se aplica dentro de las opciones 'having'.
· Caracteres Unicode: Si la consulta contiene caracteres Unicode es obligatorio usar comillas dobles. Por ejemplo, si la etiqueta es 富士山, debe escribir HAVING 'tags="富士山"' o la consulta no devolverá ningún resultado.

Ejemplo de exclusión con Having:
Obtener archivos etiquetados como "Ciencia" ignorando la etiqueta "Ciencia Ficción".

    {prog_id} tags=Ciencia HAVING "NOT tags=Ficción" """
    },
    "gl": {
        "CLI_DESC": "Unha ferramenta de busca mellorada para Baloo",
        "ARG_QUERY": "consulta [HAVING expresión] [[operador] SUBQUERY consulta [HAVING expresión]]...",
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
        "ERR_REMOVED_OPTION": "a opción {} eliminouse; use HAVING ou SUBQUERY na consulta",
        "ERR_UNKNOWN_OPTIONS": "argumentos non recoñecidos: {}",
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
  · :   - contén (só para comparación de texto) ou empeza con (para etiquetas)
  · =   - igual
  · ==  - igual en propiedades de datas para evitar a comparación de hora/minuto/segundo
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
  · tags (Nota: No se poden buscar cadeas completas como "Science Fiction", pero a búsqueda con guións baixos funciona: 'tags:Science_Fiction')
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
  · CreationDate (Formatado como aaaa-MM-dd. Nota: inconsistente en **Baloo** usando o comparador '==', pero pódese usar coas opcións 'having')
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
  · ImageDateTime (Formatado como aaaa-MM-dd. Nota: inconsistente en **Baloo** usando o comparador '==', pero pódese usar coas opcións 'having').
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

- Cláusula SUBQUERY -

A consulta principal selecciona cartafoles. Cada SUBQUERY busca independentemente dentro deles; --type aplícase aos elementos atopados. A primeira SUBQUERY inicia o conxunto: ignórase o seu AND ou OR, pero respéctase NOT. As seguintes SUBQUERY ou AND SUBQUERY intersectan resultados; AND NOT SUBQUERY réstaos; OR SUBQUERY úneos; OR NOT SUBQUERY úneos co complemento; OR EXCLUSIVE SUBQUERY calcula a diferenza simétrica (XOR).
O complemento calcúlase respecto dos elementos indexados nos cartafoles seleccionados que cumpren os filtros de tipo e data das subconsultas. AND e AND NOT teñen prioridade sobre XOR, que ten prioridade sobre OR e OR NOT. Os operadores da mesma prioridade avalíanse de esquerda a dereita.
Unha SUBQUERY baleira coincide con todos os elementos dos cartafoles seleccionados. HAVING filtra a busca inmediatamente anterior; as cláusulas HAVING baleiras ignóranse e as repetidas nunha busca únense con AND. Os nomes das cláusulas e dos operadores deben estar en maiúsculas. O límite e o desprazamento aplícanse despois de combinar os resultados.

Exemplo:
Buscar presentacións en cartafoles que coincidan con KDE, que conteñan Baloo ou Bagheera e non estean etiquetadas como Obsolete.

    {prog_id} --directory '~/Documents' KDE SUBQUERY Baloo HAVING 'NOT tags=Obsolete' OR SUBQUERY Bagheera HAVING 'NOT tags=Obsolete' --type Presentation


- Cláusula HAVING -

A cláusula HAVING permite filtrar os resultados devoltos por Baloo. Admite a sintaxe estándar de Baloo e ademais o operador 'NOT'.

Aparte, pode usar para comparar os seguintes operadores:

- '==' (igual sensible a maiúsculas/minúsculas, o comportamento non é o mesmo que '==' en Baloo)
- '!=' (non é igual)
- '!:' (non contén)
- Comparación de propiedade a propiedade (p. ex., 'width > height').
- 'created', unha propiedade específica de Bagheera para datas de creación de ficheiros (Formatado como 'aaaa-MM-dd').

Observacións importantes:
· Sensibilidade a maiúsculas: Todas as comparacións de texto son insensibles a maiúsculas a menos que se use '=='.
· Valores baleiros: Pode verificar a presenza ou ausencia de valores usando comiñas baleiras. Por exemplo, 'tags!=""' coincide con calquera ficheiro con polo menos unha etiqueta, mentres que 'tags=""' coincide con ficheiros sen etiquetas.
· Niveis de etiquetas: As comparacións realízanse contra a ruta completa da etiqueta e cada nivel individual. Un ficheiro etiquetado como 'Persoa/María Callas' coincide con 'Maria', 'Callas', 'Persoa' e a cadea completa.
· Límite de caracteres: A diferenza de Baloo, o límite mínimo de 3 caracteres para valores de cadea non se aplica dentro das opcións 'having'.
· Caracteres Unicode: Se a consulta contén caracteres Unicode é obrigatorio usar comiñas dobres. Por exemplo, se a etiqueta é 富士山, debe escribir HAVING 'tags="富士山"' ou a consulta non devolverá ningún resultado.

Exemplo de exclusión con Having:
Obter ficheiros etiquetados como "Ciencia" ignorando a etiqueta "Ciencia Ficción".

    {prog_id} tags=Ciencia HAVING "NOT tags=Ficción" """
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
