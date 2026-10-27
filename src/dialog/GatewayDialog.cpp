// SPDX-License-Identifier: GPL-2.0-or-later
#include "GatewayDialog.h"
#include <QDialogButtonBox>
#include <QHeaderView>
#include <QLabel>
#include <QPushButton>
#include <QTableWidget>
#include <QVBoxLayout>

GatewayDialog::GatewayDialog(const QList<GatewayCandidate>& candidates, bool automatic, QWidget* parent)
    : QDialog(parent)
{
    setWindowTitle(tr("Choose VPN server"));
    resize(720, 420);
    auto* layout = new QVBoxLayout(this);
    auto* status = new QLabel(automatic
        ? tr("Checking saved profiles; the lowest TCP latency will be selected automatically.")
        : tr("Checking saved profiles. Select a reachable profile, then connect."), this);
    status->setWordWrap(true);
    layout->addWidget(status);
    auto* table = new QTableWidget(candidates.size(), 3, this);
    table->setHorizontalHeaderLabels({tr("Profile"), tr("Gateway"), tr("TCP latency")});
    table->horizontalHeader()->setSectionResizeMode(QHeaderView::Stretch);
    table->setSelectionBehavior(QAbstractItemView::SelectRows);
    table->setSelectionMode(QAbstractItemView::SingleSelection);
    table->setEditTriggers(QAbstractItemView::NoEditTriggers);
    for (int i = 0; i < candidates.size(); ++i) {
        table->setItem(i, 0, new QTableWidgetItem(candidates.at(i).name));
        // Never display credentials, paths or query tokens embedded in a profile URL.
        table->setItem(i, 1, new QTableWidgetItem(candidates.at(i).url.host()));
        table->setItem(i, 2, new QTableWidgetItem(tr("Waiting")));
    }
    layout->addWidget(table);
    auto* note = new QLabel(tr("This checks direct TCP connectivity, not VPN authentication or download speed. "
        "No credentials are sent during probing. Certificate checks and login run normally after selection. "
        "Profiles configured to use a proxy are skipped."), this);
    note->setWordWrap(true);
    layout->addWidget(note);
    auto* buttons = new QDialogButtonBox(QDialogButtonBox::Ok | QDialogButtonBox::Cancel, this);
    buttons->button(QDialogButtonBox::Ok)->setText(tr("Connect selected"));
    buttons->button(QDialogButtonBox::Ok)->setEnabled(false);
    layout->addWidget(buttons);
    auto* probe = new GatewayProbe(this);
    connect(this, &QDialog::finished, probe, &GatewayProbe::cancel);
    connect(buttons, &QDialogButtonBox::rejected, this, &QDialog::reject);
    connect(buttons, &QDialogButtonBox::accepted, this, [this, table, candidates]() {
        const int row = table->currentRow();
        if (row >= 0 && table->item(row, 2)->data(Qt::UserRole).toBool()) {
            m_selected = candidates.at(row).name;
            accept();
        }
    });
    connect(table, &QTableWidget::itemSelectionChanged, this, [table, buttons]() {
        const int row = table->currentRow();
        buttons->button(QDialogButtonBox::Ok)->setEnabled(row >= 0 && table->item(row, 2)->data(Qt::UserRole).toBool());
    });
    connect(probe, &GatewayProbe::result, this, [table](int row, qint64 milliseconds, const QString& text) {
        table->item(row, 2)->setText(milliseconds >= 0 ? QString::number(milliseconds) + " ms" : text);
        table->item(row, 2)->setData(Qt::UserRole, milliseconds >= 0);
    });
    connect(probe, &GatewayProbe::finished, this, [this, table, status, buttons, candidates, automatic](int fastest) {
        if (fastest < 0) {
            status->setText(tr("No reachable direct gateway. No login was attempted."));
            return;
        }
        table->selectRow(fastest);
        buttons->button(QDialogButtonBox::Ok)->setEnabled(true);
        status->setText(tr("Probe complete. Lowest TCP latency: %1").arg(candidates.at(fastest).name));
        if (automatic) {
            m_selected = candidates.at(fastest).name;
            accept();
        }
    });
    probe->start(candidates);
}

QString GatewayDialog::selectedProfile() const
{
    return m_selected;
}
