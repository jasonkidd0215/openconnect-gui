// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
#include <QDialog>
#include "gatewayprobe.h"

class GatewayDialog : public QDialog {
public:
    GatewayDialog(const QList<GatewayCandidate>& candidates, bool automatic, QWidget* parent = nullptr);
    QString selectedProfile() const;
private:
    QString m_selected;
};
