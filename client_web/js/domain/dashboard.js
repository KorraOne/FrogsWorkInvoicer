import { formatMoney } from "./invoice_format.js";
import { isGstRegistered } from "./gst.js";

export function dashboardAmounts(bucket, gstRegistered) {
  const primary = formatMoney(bucket.inc_gst);
  const secondary = gstRegistered ? `(${formatMoney(bucket.ex_gst)} ex GST)` : "";
  return { primary, secondary };
}

export function resolveActiveBusiness(businesses, settings) {
  const names = Object.keys(businesses || {});
  if (!names.length) return { name: "", profile: {} };
  const defaultName = settings?.default_business;
  if (defaultName && businesses[defaultName]) return { name: defaultName, profile: businesses[defaultName] };
  const name = names[0];
  return { name, profile: businesses[name] };
}

export function businessGstRegistered(businesses, settings) {
  const { profile } = resolveActiveBusiness(businesses, settings);
  return isGstRegistered(profile);
}
