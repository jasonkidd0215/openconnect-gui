// SPDX-License-Identifier: GPL-2.0-or-later
#include "gatewayprobe.h"
#include <QElapsedTimer>
#include <QNetworkProxy>
#include <QTimer>

GatewayProbe::GatewayProbe(QObject* parent, int timeoutMs)
    : QObject(parent), m_timeoutMs(timeoutMs)
{
}

QUrl GatewayProbe::gatewayUrl(const QString& gateway)
{
    return QUrl(gateway.contains("://") ? gateway : "https://" + gateway, QUrl::StrictMode);
}

bool GatewayProbe::eligible(const GatewayCandidate& candidate)
{
    const auto& url = candidate.url;
    return candidate.direct && url.isValid() && url.scheme() == "https"
        && !url.host().isEmpty() && url.userInfo().isEmpty() && url.port(443) > 0;
}

void GatewayProbe::cancel()
{
    m_running = false;
    const auto sockets = m_active;
    m_active.clear();
    for (auto* socket : sockets) {
        socket->disconnect(this);
        socket->abort();
        socket->deleteLater();
    }
}

void GatewayProbe::start(const QList<GatewayCandidate>& candidates)
{
    cancel();
    m_candidates = candidates;
    m_next = 0;
    m_fastest = -1;
    m_best = -1;
    m_running = true;
    QTimer::singleShot(0, this, &GatewayProbe::pump);
}

void GatewayProbe::complete(QTcpSocket* socket, int index, qint64 elapsed, const QString& status)
{
    if (!m_running || !m_active.remove(socket))
        return;
    socket->disconnect(this);
    socket->abort();
    socket->deleteLater();
    if (elapsed >= 0 && (m_best < 0 || elapsed < m_best)) {
        m_best = elapsed;
        m_fastest = index;
    }
    emit result(index, elapsed, status);
    QTimer::singleShot(0, this, &GatewayProbe::pump);
}

void GatewayProbe::pump()
{
    if (!m_running)
        return;
    while (m_next < m_candidates.size() && m_active.size() < 6) {
        const int index = m_next++;
        const auto candidate = m_candidates.at(index);
        if (!eligible(candidate)) {
            emit result(index, -1, tr("Skipped (invalid URL or proxy profile)"));
            continue;
        }
        auto* socket = new QTcpSocket(this);
        socket->setProxy(QNetworkProxy::NoProxy);
        m_active.insert(socket);
        QElapsedTimer elapsed;
        elapsed.start();
        connect(socket, &QTcpSocket::connected, this, [this, socket, index, elapsed]() {
            complete(socket, index, elapsed.elapsed(), tr("TCP reachable"));
        });
        connect(socket, &QTcpSocket::errorOccurred, this, [this, socket, index](QAbstractSocket::SocketError) {
            complete(socket, index, -1, tr("Connection failed"));
        });
        QTimer::singleShot(m_timeoutMs, socket, [this, socket, index]() {
            complete(socket, index, -1, tr("Timed out"));
        });
        socket->connectToHost(candidate.url.host(), static_cast<quint16>(candidate.url.port(443)));
    }
    if (m_next == m_candidates.size() && m_active.isEmpty()) {
        m_running = false;
        emit finished(m_fastest);
    }
}
