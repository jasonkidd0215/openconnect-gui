// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
#include <QString>
#include <QJsonObject>

class WindowsNetwork {
public:
    bool prepare();
    bool configure(const QString& address, const QString& gateway);
    bool cleanup();
    QString error;
private:
    bool call(const QString& action, QJsonObject request, QJsonObject* response = nullptr);
    QString statePath;
};
