/** Shared FrogsWork branding footer for all outbound email. */

export const FROGSWORK_URL = "https://frogswork.com";

const COMPOSE_LINES = {
  invoice: "This invoice was composed with FrogsWork Invoicer.",
  quote: "This quote was composed with FrogsWork.",
  followup: "This reminder was composed with FrogsWork Invoicer.",
  transactional: "Sent by FrogsWork.",
};

/**
 * @param {{ variant?: 'invoice'|'quote'|'followup'|'transactional' }} [opts]
 * @returns {string[]}
 */
export function brandedFooterText({ variant = "invoice" } = {}) {
  const line = COMPOSE_LINES[variant] || COMPOSE_LINES.invoice;
  return ["", "—", line, FROGSWORK_URL];
}

/**
 * @param {{ variant?: 'invoice'|'quote'|'followup'|'transactional' }} [opts]
 */
export function brandedFooterHtml({ variant = "invoice" } = {}) {
  const line = COMPOSE_LINES[variant] || COMPOSE_LINES.invoice;
  const escaped = line
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
  return [
    `<hr style="border:none;border-top:1px solid #ddd;margin:1em 0">`,
    `<p style="margin:0 0 0.4em 0;color:#555;font-size:13px">${escaped}</p>`,
    `<p style="margin:0"><a href="${FROGSWORK_URL}">${FROGSWORK_URL}</a></p>`,
  ].join("\n");
}

/**
 * Append branded footer to plain text and optional HTML bodies.
 * @param {string} text
 * @param {string} [html]
 * @param {{ variant?: 'invoice'|'quote'|'followup'|'transactional' }} [opts]
 */
export function appendBrandedFooter(text, html, { variant = "transactional" } = {}) {
  const footerLines = brandedFooterText({ variant }).join("\n");
  const footerHtml = brandedFooterHtml({ variant });
  const nextText = `${text || ""}${footerLines}`;
  if (!html) {
    return { text: nextText, html: undefined };
  }
  return { text: nextText, html: `${html}${footerHtml}` };
}
