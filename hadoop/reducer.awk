# Hadoop Streaming reducer: keys arrive sorted; emit CURRENCY<TAB>count<TAB>total.
BEGIN { FS = "\t" }
$1 != cur { if (cur != "") printf "%s\t%d\t%.2f\n", cur, n, total; cur = $1; n = 0; total = 0 }
{ n++; total += $2 }
END { if (cur != "") printf "%s\t%d\t%.2f\n", cur, n, total }
