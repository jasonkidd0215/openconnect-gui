// SPDX-License-Identifier: GPL-2.0-or-later
#include "windowsnetwork.h"
#include <QCoreApplication>
#include <QFileInfo>
#include <QJsonDocument>
#include <QProcess>
#ifdef Q_OS_WIN
#include <windows.h>
#endif

bool WindowsNetwork::call(const QString& action, QJsonObject request, QJsonObject* response)
{
    const QString directory = QCoreApplication::applicationDirPath();
    QString python = qEnvironmentVariable("OPENCONNECT_GUI_PYTHON");
    if (python.isEmpty())
        python = directory + "/python/python.exe";
    const QString broker = directory + "/network/route_broker.py";
    if (!QFileInfo::exists(python) || !QFileInfo::exists(broker)) {
        error = "Python network runtime is missing. Use the complete Windows package.";
        return false;
    }
    request["owner"] = static_cast<qint64>(QCoreApplication::applicationPid());
    QProcess process;
#ifdef Q_OS_WIN
    process.setCreateProcessArgumentsModifier([](QProcess::CreateProcessArguments* args) {
        args->flags |= CREATE_NO_WINDOW;
    });
#endif
    process.start(python, {"-X", "utf8", broker, action});
    if (!process.waitForStarted(10000)) {
        error = "Could not start the network manager.";
        return false;
    }
    process.write(QJsonDocument(request).toJson(QJsonDocument::Compact));
    process.closeWriteChannel();
    if (!process.waitForFinished(90000)) {
        // Let the bounded helper finish rather than terminate a route mutation midway.
        process.waitForFinished(-1);
    }
    if (process.exitStatus() != QProcess::NormalExit || process.exitCode() != 0) {
        error = QString::fromUtf8(process.readAllStandardError()).trimmed();
        if (error.isEmpty())
            error = "Network manager failed.";
        return false;
    }
    const auto document = QJsonDocument::fromJson(process.readAllStandardOutput());
    if (!document.isObject()) {
        error = "Network manager returned invalid state.";
        return false;
    }
    if (response)
        *response = document.object();
    return true;
}

bool WindowsNetwork::prepare()
{
    if (!statePath.isEmpty() && !cleanup())
        return false;
    QJsonObject response;
    if (!call("prepare", {}, &response))
        return false;
    statePath = response["state"].toString();
    return !statePath.isEmpty();
}

bool WindowsNetwork::configure(const QString& address, const QString& gateway)
{
    return call("configure", {{"state",statePath},{"address",address},{"gateway",gateway}});
}

bool WindowsNetwork::cleanup()
{
    if (statePath.isEmpty())
        return true;
    if (!call("cleanup", {{"state",statePath}}))
        return false;
    statePath.clear();
    return true;
}
