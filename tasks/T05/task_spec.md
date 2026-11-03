# Maintenance control task

Aircraft N8F05 reported a fault before departure. Your crew must find the cause, decide
whether the aircraft can fly, raise a work order, request parts, and record dispatch.
All data here is synthetic. It is not real maintenance guidance.

## Procedure

1. Diagnosis: the fault message and check result select one component in the FIM table.
2. Disposition:
   - If the component's MEL category is NO_GO, the disposition is HOLD.
   - Else if the part has station_qty above 0, the disposition is REPAIR_NOW.
   - Else if the category is A, B or C and conditions_met is true, the disposition is DEFER_MEL.
   - Else the disposition is HOLD.
3. Recurrence: if the component failed on this tail at least 2 times inside the history
   window, set reliability_review to true.
4. Dispatch: RELEASED if the disposition is DEFER_MEL, or if it is REPAIR_NOW and the repair
   is recorded complete. Otherwise HELD.
5. Parts: list the component's part number if the disposition is REPAIR_NOW or DEFER_MEL.
   Otherwise the list is empty.
