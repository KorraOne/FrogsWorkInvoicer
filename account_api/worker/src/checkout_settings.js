export async function isDefaultBeta80Enabled(db) {
  const row = await db
    .prepare("SELECT default_beta80_enabled FROM checkout_promo_settings WHERE id = 1")
    .first();
  return Boolean(row?.default_beta80_enabled);
}

export async function setDefaultBeta80Enabled(db, enabled) {
  const now = new Date().toISOString();
  await db
    .prepare(
      `INSERT INTO checkout_promo_settings (id, default_beta80_enabled, updated_at)
       VALUES (1, ?, ?)
       ON CONFLICT(id) DO UPDATE SET
         default_beta80_enabled = excluded.default_beta80_enabled,
         updated_at = excluded.updated_at`
    )
    .bind(enabled ? 1 : 0, now)
    .run();
  return enabled;
}

export async function getCheckoutPromoAdminContext(db) {
  return { default_beta80_enabled: await isDefaultBeta80Enabled(db) };
}

async function resolvePromotionCodeId(stripe, code) {
  const normalized = (code || "").trim();
  if (!normalized) return null;
  const list = await stripe.promotionCodes.list({
    code: normalized,
    active: true,
    limit: 1,
  });
  return list.data[0]?.id || null;
}

export async function buildCheckoutDiscounts(env, db, stripe, body) {
  const adminDefault = await isDefaultBeta80Enabled(db);
  const promoId = (env.STRIPE_PROMO_BETA80 || "").trim();

  if (adminDefault && promoId) {
    return {
      discounts: [{ promotion_code: promoId }],
      allow_promotion_codes: true,
    };
  }

  const urlCode = (body.promotion_code || "").trim();
  if (urlCode && stripe) {
    const resolved = await resolvePromotionCodeId(stripe, urlCode);
    if (resolved) {
      return {
        discounts: [{ promotion_code: resolved }],
        allow_promotion_codes: true,
      };
    }
  }

  return { discounts: undefined, allow_promotion_codes: true };
}
