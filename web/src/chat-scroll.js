// Pure scroll policy for the VP chat. Kept separate from the JSX so the
// three behaviours the owner cares about are testable without a browser:
//   - a scrolled-up reader is NOT pulled down by a new message;
//   - an at-bottom reader follows a new message;
//   - the explicit affordance/own send always goes to the bottom once.
export const NEAR_BOTTOM_PX = 80;

export function isNearBottom({ scrollTop, scrollHeight, clientHeight }, threshold = NEAR_BOTTOM_PX) {
  return scrollHeight - scrollTop - clientHeight < threshold;
}

export function shouldFollow({ atBottom, ownSend = false, jump = false }) {
  // A jump to a search result is deliberate navigation; the reader chose it.
  if (jump) return true;
  return Boolean(ownSend) || Boolean(atBottom);
}
