# Hadoop Streaming mapper: CSV receipt -> "CURRENCY<TAB>amount".
# The apache/hadoop image ships no Python, so the mapper/reducer are awk.
# Header, malformed, non-positive and unknown-currency rows are dropped and
# reported through a Hadoop counter (stderr "reporter:counter:" protocol).
BEGIN { FS = ","; valid["INR"]; valid["USD"]; valid["EUR"]; valid["GBP"] }
NF != 7 || $1 == "receipt_id" { next }
{
  if ($4 !~ /^[0-9]+(\.[0-9]+)?$/ || $4 + 0 <= 0 || !($5 in valid)) {
    print "reporter:counter:receipts,bad_rows,1" > "/dev/stderr"; next
  }
  printf "%s\t%.2f\n", $5, $4
}
