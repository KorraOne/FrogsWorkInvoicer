import { confirmSheet } from "../components/ui";

type LeaveGuard = () => Promise<boolean>;

let leaveGuard: LeaveGuard | null = null;
let lastAllowedHash = "";

export function setLeaveGuard(fn: LeaveGuard | null) {
  leaveGuard = fn;
}

export function clearLeaveGuard() {
  leaveGuard = null;
}

/** Serialize form controls for dirty comparison. */
export function serializeForm(form: HTMLFormElement): string {
  const fd = new FormData(form);
  const parts: string[] = [];
  for (const [k, v] of fd.entries()) {
    parts.push(`${k}=${typeof v === "string" ? v : "[file]"}`);
  }
  form.querySelectorAll("input[disabled][name], select[disabled][name], textarea[disabled][name]").forEach((el) => {
    const input = el as HTMLInputElement;
    parts.push(`${input.name}=${input.value}`);
  });
  return parts.sort().join("&");
}

/**
 * Watch a form for unsaved changes. Sets a global leave guard for tab/hash navigation.
 * Call `clear()` after successful save; use `attemptLeave(go)` for Back/Cancel.
 */
export function attachUnsavedGuard(form: HTMLFormElement): {
  clear: () => void;
  attemptLeave: (go: () => void) => Promise<void>;
  isDirty: () => boolean;
} {
  let baseline = serializeForm(form);
  let dirty = false;

  const refreshDirty = () => {
    dirty = serializeForm(form) !== baseline;
  };

  form.addEventListener("input", refreshDirty);
  form.addEventListener("change", refreshDirty);

  const ask = async () => {
    refreshDirty();
    if (!dirty) return true;
    return confirmSheet("You have unsaved changes. Leave without saving?", "Leave");
  };

  setLeaveGuard(ask);

  return {
    isDirty: () => {
      refreshDirty();
      return dirty;
    },
    clear: () => {
      dirty = false;
      baseline = serializeForm(form);
      clearLeaveGuard();
    },
    attemptLeave: async (go) => {
      if (!(await ask())) return;
      clearLeaveGuard();
      go();
    },
  };
}

/** Call before handling a route change. Returns false if navigation should be aborted. */
export async function allowNavigation(): Promise<boolean> {
  if (!leaveGuard) return true;
  const ok = await leaveGuard();
  if (ok) clearLeaveGuard();
  return ok;
}

export function rememberAllowedHash(hash: string) {
  lastAllowedHash = hash || "#home";
}

export function getLastAllowedHash() {
  return lastAllowedHash || "#home";
}
