import crypto from "crypto";
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const money = (n) => (Math.round((Number(n) + Number.EPSILON) * 100) / 100).toFixed(2);
const incGst = (ex) => money(Number(ex) * 1.1);
const daysAgo = (d) => {
  const x = new Date();
  x.setUTCDate(x.getUTCDate() - d);
  return x.toISOString().slice(0, 10);
};
const esc = (s) => String(s).replace(/'/g, "''");
const biz = "Sam Chen — Garden & Property";

function inv(number, customer, days, desc, ex, status, sentDays, paidDays) {
  const id = crypto.randomUUID();
  const invDate = daysAgo(days);
  const due = new Date(invDate + "T12:00:00Z");
  due.setUTCDate(due.getUTCDate() + 14);
  const dueIso = due.toISOString().slice(0, 10);
  const padded = String(number).padStart(8, "0");
  const data = {
    invoice_id: id,
    invoice_number: number,
    invoice_date: invDate,
    customer_name: customer,
    business_name: biz,
    description: desc,
    amount_ex_gst: money(ex),
    taxable_ex_gst: money(ex),
    gst_free_ex_gst: "0.00",
    gst_amount: money(ex * 0.1),
    total_inc_gst: incGst(ex),
    gst_registered: true,
    line_items: [
      {
        description: desc,
        quantity: 1,
        unit_amount_ex_gst: money(ex),
        amount_ex_gst: money(ex),
        gst_applicable: true,
        gst_free: false,
      },
    ],
    filename: `Invoice_${padded}_${invDate}.pdf`,
    status,
    sent_date: sentDays != null ? daysAgo(sentDays) : null,
    paid_date: paidDays != null ? daysAgo(paidDays) : null,
    due_date: dueIso,
    due_rule_type: "net_days",
    due_net_days: 14,
    pdf_status: "pending",
  };
  return { id, number, json: esc(JSON.stringify(data)) };
}

const specs = [
  inv(1, "Harbour View Cafe", 2, "Monthly grounds maintenance — March", 880, "not_sent"),
  inv(2, "Margaret Nguyen", 0, "Hedge trim and green waste removal", 420, "not_sent"),
  inv(3, "Pelican Point Strata", 18, "Common-area garden refresh", 2400, "sent", 15),
  inv(4, "West Coast Electrical", 10, "Site clearance before cable run", 650, "sent", 8),
  inv(5, "Old Port Gallery", 5, "Courtyard repaving prep and labour", 3200, "sent", 3),
  inv(6, "Harbour View Cafe", 52, "Irrigation repair and mulch top-up", 1500, "paid", 49, 35),
  inv(7, "Pelican Point Strata", 28, "Seasonal prune — north garden bed", 990, "paid", 26, 12),
  inv(8, "Margaret Nguyen", 14, "Lawn restoration and fertiliser", 450, "paid", 12, 2),
];

const ts = new Date().toISOString();
const bizJson = esc(
  JSON.stringify({
    address: "Unit 4, 18 Kingsley Street\nFremantle WA 6160",
    abn: "51824793601",
    gst_registered: true,
    account_name: "Sam Chen",
    bsb: "016-001",
    acc: "284719",
    invoice_counter: 10,
  })
);

const customers = {
  "Harbour View Cafe": {
    address: "42 Marine Terrace\nFremantle WA 6160",
    abn: "87145632109",
    email: "accounts@harbourviewcafe.example",
  },
  "Pelican Point Strata": {
    address: "C/- Ace Body Corporate\nPO Box 120\nNorth Fremantle WA 6159",
    abn: "99631478523",
    email: "levies@pelicanpointstrata.example",
  },
  "West Coast Electrical": {
    address: "7 Forge Street\nO'Connor WA 6163",
    abn: "",
    email: "payables@westcoastelectrical.example",
  },
  "Margaret Nguyen": {
    address: "15 Pine Avenue\nPalmyra WA 6157",
    abn: "",
    email: "margaret.nguyen@example.com",
  },
  "Old Port Gallery": {
    address: "22 Henry Street\nFremantle WA 6160",
    abn: "53098741256",
    email: "",
  },
};

const settings = esc(
  JSON.stringify({
    due_rule_type: "net_days",
    due_net_days: 14,
    welcome_complete: true,
    default_business: biz,
  })
);

const sql = [];
sql.push("DELETE FROM email_outbox;");
sql.push("DELETE FROM doc_invoices;");
sql.push("DELETE FROM doc_businesses;");
sql.push("DELETE FROM doc_customers;");
sql.push("DELETE FROM doc_settings;");
sql.push("DELETE FROM guest_workspaces;");
sql.push(
  `INSERT INTO doc_businesses (user_id, name, data_json, revision, updated_at) VALUES (4, '${esc(biz)}', '${bizJson}', 1, '${ts}');`
);
for (const [name, data] of Object.entries(customers)) {
  sql.push(
    `INSERT INTO doc_customers (user_id, name, data_json, revision, updated_at) VALUES (4, '${esc(name)}', '${esc(JSON.stringify(data))}', 1, '${ts}');`
  );
}
sql.push(
  `INSERT INTO doc_settings (user_id, data_json, revision, updated_at) VALUES (4, '${settings}', 1, '${ts}');`
);
for (const s of specs) {
  sql.push(
    `INSERT INTO doc_invoices (user_id, invoice_key, invoice_number, data_json, revision, updated_at, pdf_status, pdf_r2_key) VALUES (4, '${s.id}', ${s.number}, '${s.json}', 1, '${ts}', 'pending', NULL);`
  );
}
sql.push("UPDATE users SET storage_tier='local' WHERE id=1;");
sql.push("UPDATE users SET storage_tier='cloud' WHERE id=4;");

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const out = path.join(__dirname, "..", "..", "migrations", "_tmp_purge_seed.sql");
fs.mkdirSync(path.dirname(out), { recursive: true });
fs.writeFileSync(out, sql.join("\n") + "\n");
console.log(out);
console.log("invoices", specs.length);
