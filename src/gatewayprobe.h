// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once

#include <QObject>
#include <QList>
#include <QSet>
#include <QTcpSocket>
#include <QUrl>

struct GatewayCandidate {
    QString name;
    QUrl url;
    bool direct = true;
};

// Reachability only: sends no TLS, HTTP, authentication or VPN payload.
class GatewayProbe : public QObject {
    Q_OBJECT
public:
    explicit GatewayProbe(QObject* parent = nullptr, int timeoutMs = 3000);
    void start(const QList<GatewayCandidate>& candidates);
    void cancel();
    static QUrl gatewayUrl(const QString& gateway);
    static bool eligible(const GatewayCandidate& candidate);

signals:
    void result(int index, qint64 milliseconds, const QString& status);
    void finished(int fastestIndex);

private:
    void pump();
    void complete(QTcpSocket* socket, int index, qint64 elapsed, const QString& status);
    QList<GatewayCandidate> m_candidates;
    QSet<QTcpSocket*> m_active;
    int m_next = 0;
    int m_fastest = -1;
    qint64 m_best = -1;
    int m_timeoutMs;
    bool m_running = false;
};
