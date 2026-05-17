#include <Baloo/Query>
#include <Baloo/ResultIterator>
#include <KFileMetaData/ExtractorCollection>
#include <KFileMetaData/SimpleExtractionResult>
#include <KFileMetaData/PropertyInfo>
#include <QMimeDatabase>
#include <QString>
#include <QStringList>
#include <QJsonDocument>
#include <QJsonObject>
#include <QJsonArray>
#include <vector>
#include <string>

// Use extern "C" to avoid C++ name mangling
extern "C" {

    // Add the attribute to force public visibility of the symbol
    __attribute__((visibility("default")))
    const char* execute_baloo_query(const char* options_json) {
        // Parse JSON options
        QJsonDocument doc = QJsonDocument::fromJson(options_json);
        QJsonObject options = doc.object();

        Baloo::Query q;

        if (options.contains("query")) {
            q.setSearchString(options["query"].toString());
        }
        if (options.contains("limit")) {
            q.setLimit(options["limit"].toInt());
        }
        if (options.contains("offset")) {
            q.setOffset(options["offset"].toInt());
        }
        if (options.contains("type")) {
            q.addType(options["type"].toString());
        }
        if (options.contains("directory")) {
            q.setIncludeFolder(options["directory"].toString());
        }
        if (options.contains("year")) {
            if (options.contains("month")) {
                if (options.contains("day")) {
                    q.setDateFilter(options["year"].toInt(), options["month"].toInt(), options["day"].toInt());
                } else {
                    q.setDateFilter(options["year"].toInt(), options["month"].toInt(), 0);
                }
            } else {
                q.setDateFilter(options["year"].toInt(), 0, 0);
            }
        }
        if (options.contains("sort")) {
            if (options["sort"].toString() == QStringLiteral("auto")) {
                 q.setSortingOption(Baloo::Query::SortNone);
            } else if (options["sort"].toString() == QStringLiteral("none")) {
                 q.setSortingOption(Baloo::Query::SortAuto);
            }
        }

        Baloo::ResultIterator it = q.exec();
        QJsonArray results;

        while (it.next()) {
            QJsonObject result;
            result["path"] = it.filePath();
            result["id"] = QString::fromUtf8(it.documentId());
            results.append(result);
        }

        QJsonDocument responseDoc(results);
        static std::string output;
        output = responseDoc.toJson(QJsonDocument::Compact).toStdString();

        return output.c_str();
    }
}

extern "C" {
    // Force visibility so ctypes can see it
    __attribute__((visibility("default")))
    const char* get_file_properties(const char* path) {
        QString filePath = QString::fromUtf8(path);

        // Detect MIME type
        QMimeDatabase mimeDb;
        QString mimeType = mimeDb.mimeTypeForFile(filePath).name();

        // Get extractors for that type
        KFileMetaData::ExtractorCollection extractors;
        QList<KFileMetaData::Extractor*> exList = extractors.fetchExtractors(mimeType);

        // Extract metadata
        KFileMetaData::SimpleExtractionResult result(filePath, mimeType);
        for (KFileMetaData::Extractor* ex : exList) {
            ex->extract(&result);
        }

        const auto props = result.properties();
        if (props.isEmpty()) return "";

        static std::string output;
        output = "";

        // Format the properties as a simple string: "Key:Value|Key:Value"
        for (auto it = props.constBegin(); it != props.constEnd(); ++it) {
            KFileMetaData::PropertyInfo pi(it.key());

            output += pi.name().toStdString() + ":" + it.value().toString().toStdString() + "|";
        }

        return output.c_str();
    }
}
