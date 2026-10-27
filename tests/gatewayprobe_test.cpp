// SPDX-License-Identifier: GPL-2.0-or-later
#include "gatewayprobe.h"
#include <QTcpServer>
#include <QSignalSpy>
#include <QtTest>

class ProbeTest : public QObject {
    Q_OBJECT
private slots:
    void rejectsUnsafeAndProxyProfiles()
    {
        QVERIFY(GatewayProbe::eligible({"ok", GatewayProbe::gatewayUrl("example.org:8443"), true}));
        QVERIFY(!GatewayProbe::eligible({"proxy", GatewayProbe::gatewayUrl("example.org"), false}));
        QVERIFY(!GatewayProbe::eligible({"http", GatewayProbe::gatewayUrl("http://example.org"), true}));
        QVERIFY(!GatewayProbe::eligible({"secret", GatewayProbe::gatewayUrl("https://user:pass@example.org"), true}));
        QVERIFY(!GatewayProbe::eligible({"empty", GatewayProbe::gatewayUrl(""), true}));
        QVERIFY(!GatewayProbe::eligible({"port", GatewayProbe::gatewayUrl("example.org:0"), true}));
    }

    void reachableServerReceivesNoPayload()
    {
        QTcpServer server;
        QVERIFY(server.listen(QHostAddress::LocalHost));
        GatewayProbe probe;
        QSignalSpy results(&probe, &GatewayProbe::result);
        QSignalSpy done(&probe, &GatewayProbe::finished);
        probe.start({{"local", GatewayProbe::gatewayUrl(QString("127.0.0.1:%1").arg(server.serverPort())), true}});
        QVERIFY(done.wait(5000));
        QCOMPARE(done.count(), 1);
        QCOMPARE(done.at(0).at(0).toInt(), 0);
        QCOMPARE(results.count(), 1);
        QVERIFY(results.at(0).at(1).toLongLong() >= 0);
        QTRY_VERIFY(server.hasPendingConnections());
        auto* peer = server.nextPendingConnection();
        QTRY_COMPARE(peer->state(), QAbstractSocket::UnconnectedState);
        QCOMPARE(peer->readAll().size(), 0);
        delete peer;
    }

    void refusalDoesNotBecomeCandidate()
    {
        QTcpServer server;
        QVERIFY(server.listen(QHostAddress::LocalHost));
        const auto port = server.serverPort();
        server.close();
        GatewayProbe probe;
        QSignalSpy done(&probe, &GatewayProbe::finished);
        probe.start({{"closed", GatewayProbe::gatewayUrl(QString("127.0.0.1:%1").arg(port)), true}});
        QVERIFY(done.wait(5000));
        QCOMPARE(done.at(0).at(0).toInt(), -1);
    }

    void cancellationSuppressesCompletion()
    {
        GatewayProbe probe;
        QSignalSpy done(&probe, &GatewayProbe::finished);
        probe.start({{"local", GatewayProbe::gatewayUrl("127.0.0.1:9"), true}});
        probe.cancel();
        QTest::qWait(50);
        QCOMPARE(done.count(), 0);
    }

    void multipleBatchesFinishOnce()
    {
        QTcpServer server;
        QVERIFY(server.listen(QHostAddress::LocalHost));
        QList<GatewayCandidate> candidates;
        for (int i = 0; i < 15; ++i)
            candidates.append({QString::number(i), GatewayProbe::gatewayUrl(QString("127.0.0.1:%1").arg(server.serverPort())), true});
        GatewayProbe probe;
        QSignalSpy results(&probe, &GatewayProbe::result);
        QSignalSpy done(&probe, &GatewayProbe::finished);
        probe.start(candidates);
        QVERIFY(done.wait(5000));
        QCOMPARE(results.count(), 15);
        QTest::qWait(50);
        QCOMPARE(done.count(), 1);
        QVERIFY(done.at(0).at(0).toInt() >= 0);
    }
};
QTEST_MAIN(ProbeTest)
#include "gatewayprobe_test.moc"
