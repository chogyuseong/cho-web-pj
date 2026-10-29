/* Late responses update their own option without taking over another course. */
function commitPlanChange(oldId, updated) {
  if (!replaceInList(oldId, updated)) return false;
  if (selected?.id !== oldId) return false;
  selected = updated;
  locks = new Set(Object.keys(updated.conditions.locked || {}).map(Number));
  renderResults();
  renderDetail();
  return true;
}
