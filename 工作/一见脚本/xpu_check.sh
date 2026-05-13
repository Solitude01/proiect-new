cat >/tmp/xpu_check.sh <<'EOF'
#!/usr/bin/env bash
set +e

XPU_SMI_CMD="${XPU_SMI_CMD:-xpu_smi}"

section() {
  printf '\n===== %s =====\n' "$1"
}

tmp_nodes=$(mktemp)
tmp_pods=$(mktemp)
tmp_actual_devices=$(mktemp)
tmp_actual_procs=$(mktemp)
tmp_actual_summary=$(mktemp)

trap 'rm -f "$tmp_nodes" "$tmp_pods" "$tmp_actual_devices" "$tmp_actual_procs" "$tmp_actual_summary"' EXIT

# NODE TYPE TOTAL INTERNAL_IP
kubectl get nodes \
  -o custom-columns=NODE:.metadata.name,TYPE:.metadata.labels."tianniu\.baidu-int\.com/xpu-type",TOTAL:.status.capacity."baidu\.com/xpu-mem",INTERNAL_IP:.status.addresses[?\(@.type==\"InternalIP\"\)].address \
  --no-headers > "$tmp_nodes"

kubectl get pods -A \
  -o custom-columns=NS:.metadata.namespace,POD:.metadata.name,NODE:.spec.nodeName,XPUMEM:.spec.containers[*].resources.limits."baidu\.com/xpu-mem" \
  --no-headers > "$tmp_pods"

get_local_node_name() {
  local hostname_name
  local local_ips

  hostname_name="$(hostname 2>/dev/null)"
  local_ips="$(hostname -I 2>/dev/null | tr ' ' '\n')"

  awk -v hn="$hostname_name" -v ips="$local_ips" '
BEGIN {
  split(ips, ip_arr, "\n")
  for (i in ip_arr) {
    if (ip_arr[i] != "") local_ip[ip_arr[i]] = 1
  }
}
{
  node = $1
  ip = $4

  if (node == hn || local_ip[ip]) {
    print node
    exit
  }
}
' "$tmp_nodes"
}

parse_xpu_smi() {
  local node="$1"

  awk -v node="$node" '
function trim(s) {
  gsub(/^[ \t]+|[ \t]+$/, "", s)
  return s
}
function num(s) {
  gsub(/^[ \t]+|[ \t]+$/, "", s)
  if (s ~ /[kK]$/)      { sub(/[kK]$/, "", s);      return s * 1000 }
  if (s ~ /[mM]$/)      { sub(/[mM]$/, "", s);      return s * 1000000 }
  if (s ~ /[gG]$/)      { sub(/[gG]$/, "", s);      return s * 1000000000 }
  gsub(/[^0-9.]/, "", s)
  return s + 0
}
BEGIN {
  mode = ""
  last_dev = ""
}
$0 ~ /^  DEVICES/ {
  mode = "dev"
  next
}
$0 ~ /^  VIDEO/ {
  mode = "video"
  next
}
$0 ~ /^  PROCESSES/ {
  mode = "proc"
  next
}

mode == "dev" && $0 ~ /^\|[ \t]*[0-9]+[ \t]*\|/ {
  split($0, a, "|")

  dev_id = trim(a[2])
  model  = trim(a[4])
  state  = trim(a[7])
  util   = num(trim(a[8]))
  mem    = trim(a[10])
  power  = num(trim(a[11]))
  temp   = num(trim(a[12]))

  split(mem, m, "/")
  used  = num(m[1])
  total = num(m[2])
  free  = total - used

  printf "%s\t%s\t%s\t%s\t%d\t%d\t%d\t%d\t%d\t%d\n", \
    node, dev_id, model, state, util, used, total, free, power, temp >> ENVIRON["TMP_ACTUAL_DEVICES"]

  next
}

mode == "proc" && $0 ~ /^\|/ {
  split($0, a, "|")

  dev_id  = trim(a[2])
  pid     = trim(a[3])
  streams = trim(a[4])
  l3      = trim(a[5])
  mem     = trim(a[6])
  cmd     = trim(a[7])

  if (dev_id != "") {
    last_dev = dev_id
  }

  if (pid ~ /^[0-9]+$/) {
    printf "%s\t%s\t%s\t%s\t%s\t%d\t%s\n", \
      node, last_dev, pid, streams, l3, num(mem), cmd >> ENVIRON["TMP_ACTUAL_PROCS"]
  }

  next
}
'
}

export TMP_ACTUAL_DEVICES="$tmp_actual_devices"
export TMP_ACTUAL_PROCS="$tmp_actual_procs"

local_node="$(get_local_node_name)"

if [ -n "$local_node" ]; then
  xpu_out="$(${XPU_SMI_CMD} 2>/dev/null)"
  xpu_rc=$?

  if [ "$xpu_rc" -eq 0 ]; then
    printf "%s\n" "$xpu_out" | parse_xpu_smi "$local_node"
  fi
fi

awk -F '\t' '
{
  node = $1
  util = $5 + 0
  used = $6 + 0
  total = $7 + 0
  temp = $10 + 0

  used_sum[node] += used
  total_sum[node] += total
  util_sum[node] += util
  card_cnt[node] += 1

  if (temp > max_temp[node]) {
    max_temp[node] = temp
  }
}
END {
  for (n in total_sum) {
    free = total_sum[n] - used_sum[n]
    usage = total_sum[n] > 0 ? used_sum[n] / total_sum[n] * 100 : 0
    avg_util = card_cnt[n] > 0 ? util_sum[n] / card_cnt[n] : 0

    printf "%s\t%d\t%d\t%d\t%.2f\t%.2f\t%d\n", \
      n, total_sum[n], used_sum[n], free, usage, avg_util, max_temp[n]
  }
}
' "$tmp_actual_devices" > "$tmp_actual_summary"

section "1) 节点 XPU 汇总：K8s 申请量 vs 本机实际消耗"
printf "%-18s %-15s %-15s %12s %12s %12s %12s %12s %12s %10s %10s %10s %12s\n" \
  "NODE" "INTERNAL_IP" "XPU_TYPE" "K8S_TOTAL" "K8S_USED" "K8S_FREE" "REAL_TOTAL" "REAL_USED" "REAL_FREE" "REAL_USE" "AVG_UTIL" "MAX_TEMP" "REAL-K8S"

awk '
function add_mem_fields(start,    i, j, arr, v, val, sum) {
  sum = 0
  for (i = start; i <= NF; i++) {
    split($i, arr, ",")
    for (j in arr) {
      v = arr[j]
      gsub(/^[ \t]+|[ \t]+$/, "", v)
      val = v + 0
      if (v ~ /[kK]$/)      val *= 1000
      else if (v ~ /[mM]$/) val *= 1000000
      else if (v ~ /[gG]$/) val *= 1000000000
      if (val > 0) sum += val
    }
  }
  return sum
}

ARGIND == 1 {
  if ($1 != "" && $3 ~ /^[0-9]+$/) {
    total[$1] = $3 + 0
    type[$1] = $2
    ip[$1] = $4

    if (type[$1] == "<none>" || type[$1] == "") type[$1] = "-"
    if (ip[$1] == "<none>" || ip[$1] == "") ip[$1] = "-"
  }
  next
}

ARGIND == 2 {
  node = $3
  if (node == "" || node == "<none>") next

  mem = add_mem_fields(4)
  if (mem > 0) {
    k8s_used[node] += mem
  }
  next
}

ARGIND == 3 {
  real_total[$1] = $2 + 0
  real_used[$1] = $3 + 0
  real_free[$1] = $4 + 0
  real_usage[$1] = $5 + 0
  avg_util[$1] = $6 + 0
  max_temp[$1] = $7 + 0
  next
}

END {
  for (n in total) {
    ku = k8s_used[n] + 0
    kf = total[n] - ku

    if (!(n in real_total)) {
      printf "%-18s %-15s %-15s %12d %12d %12d %12s %12s %12s %10s %10s %10s %12s\n", \
        n, ip[n], type[n], total[n], ku, kf, "N/A", "N/A", "N/A", "N/A", "N/A", "N/A", "N/A"
      continue
    }

    rt = real_total[n] + 0
    ru = real_used[n] + 0
    rf = real_free[n] + 0
    rg = real_usage[n] + 0
    au = avg_util[n] + 0
    mt = max_temp[n] + 0
    diff = ru - ku

    printf "%-18s %-15s %-15s %12d %12d %12d %12d %12d %12d %9.2f%% %9.2f%% %9dC %12d\n", \
      n, ip[n], type[n], total[n], ku, kf, rt, ru, rf, rg, au, mt, diff
  }
}
' "$tmp_nodes" "$tmp_pods" "$tmp_actual_summary" | sort -k1,1

section "2) 本机单卡实际消耗明细：来自 xpu_smi"
printf "%-18s %6s %-8s %-6s %8s %12s %12s %12s %10s %8s\n" \
  "NODE" "DevID" "Model" "State" "UseRate" "USED_MB" "TOTAL_MB" "FREE_MB" "Power(W)" "Temp"

if [ -s "$tmp_actual_devices" ]; then
  awk -F '\t' '
  {
    printf "%-18s %6s %-8s %-6s %7d%% %12d %12d %12d %10d %7dC\n", \
      $1, $2, $3, $4, $5, $6, $7, $8, $9, $10
  }
  ' "$tmp_actual_devices" | sort -k1,1 -k2,2n
  awk -F '\t' '
  {
    used+=$6; total+=$7; free+=$8; power+=$9; util+=$5; cnt++
  }
  END {
    if (cnt > 0)
      printf "%-18s %6s %-8s %-6s %6.1f%% %12d %12d %12d %10d %7s\n", \
        "[合计]", "", "", "", util/cnt, used, total, free, power, ""
  }' "$tmp_actual_devices"
else
  echo "本机未采集到 xpu_smi 数据"
fi

section "3) 本机 XPU 进程实际消耗明细：来自 xpu_smi"
printf "%-18s %6s %10s %8s %10s %10s %-20s\n" \
  "NODE" "DevID" "PID" "Streams" "L3" "MEM_MB" "Command"

if [ -s "$tmp_actual_procs" ]; then
  awk -F '\t' '
  {
    printf "%-18s %6s %10s %8s %10s %10d %-20s\n", \
      $1, $2, $3, $4, $5, $6, $7
  }
  ' "$tmp_actual_procs" | sort -k1,1 -k2,2n -k6,6nr
  awk -F '\t' '
  { mem+=$6; cnt++ }
  END {
    if (cnt > 0)
      printf "%-18s %6s %10d %8s %10s %10d %-20s\n", \
        "[合计]", "", cnt, "", "", mem, "(进程数/总内存MiB)"
  }' "$tmp_actual_procs"
else
  echo "本机未采集到 XPU 进程数据"
fi

section "4) XPU Pod 申请明细：来自 K8s limits"
printf "%-12s %-48s %-18s %12s\n" "空间" "Pod" "节点" "申请MiB"

awk '
function add_mem_fields(start,    i, j, arr, v, val, sum) {
  sum = 0
  for (i = start; i <= NF; i++) {
    split($i, arr, ",")
    for (j in arr) {
      v = arr[j]
      gsub(/^[ \t]+|[ \t]+$/, "", v)
      val = v + 0
      if (v ~ /[kK]$/)      val *= 1000
      else if (v ~ /[mM]$/) val *= 1000000
      else if (v ~ /[gG]$/) val *= 1000000000
      if (val > 0) sum += val
    }
  }
  return sum
}
{
  if ($1 == "" || $1 == "<none>") next

  mem = add_mem_fields(4)

  if (mem > 0) {
    printf "%-12s %-48s %-18s %12d\n", $1, $2, $3, mem
  }
}
' "$tmp_pods" | sort -k3,3 -k4,4nr

awk '
function add_mem_fields(start,    i, j, arr, v, val, sum) {
  sum = 0
  for (i = start; i <= NF; i++) {
    split($i, arr, ",")
    for (j in arr) {
      v = arr[j]
      gsub(/^[ \t]+|[ \t]+$/, "", v)
      val = v + 0
      if (v ~ /[kK]$/)      val *= 1000
      else if (v ~ /[mM]$/) val *= 1000000
      else if (v ~ /[gG]$/) val *= 1000000000
      if (val > 0) sum += val
    }
  }
  return sum
}
{
  if ($1 == "" || $1 == "<none>") next
  mem = add_mem_fields(4)
  if (mem > 0) {
    pod_cnt++
    pod_mem += mem
    ns_set[$1] = 1
    if ($3 != "" && $3 != "<none>") node_set[$3] = 1
  }
}
END {
  for (n in ns_set) ns_cnt++
  for (n in node_set) node_cnt++
  printf "%-12s %-48s %-18s %12d\n", \
    "[合计]", "(Pod:" pod_cnt " 空间:" ns_cnt " 节点:" node_cnt ")", "", pod_mem
}
' "$tmp_pods"

section "5) Deployment 副本情况"
printf "%-10s %-40s %10s %10s\n" "空间" "名称" "期望副本" "可用副本"

kubectl get deployments -n default \
  -o custom-columns=NAME:.metadata.name,DESIRED:.spec.replicas,AVAILABLE:.status.availableReplicas \
  --no-headers | awk '
$1 ~ /^ep-/ || $1 == "tn-controller-manager-ep-package" {
  desired = $2
  available = $3

  if (desired == "<none>" || desired == "") desired = 0
  if (available == "<none>" || available == "") available = 0

  printf "%-10s %-40s %10s %10s\n", "default", $1, desired, available
  cnt++
  tot_desired += desired
  tot_available += available
}
END {
  if (cnt > 0)
    printf "%-10s %-40s %10d %10d\n", "[合计]", "(共" cnt "个Deployment)", tot_desired, tot_available
}'

# ─────────────────────────────────────────────────────────
# section 6: 结构化摘要（中心端聚合专用，请勿删除）
# 格式: ##XPUSMI## IP REAL_TOTAL REAL_USED REAL_FREE USAGE% AVG_UTIL% MAX_TEMP MODEL DEV_CNT
# ─────────────────────────────────────────────────────────
section "6) 结构化摘要（中心端聚合专用）"

_lip=$(hostname -I 2>/dev/null | awk '{print $1}')

if [ -s "$tmp_actual_devices" ]; then
  awk -F'\t' -v lip="$_lip" '
  BEGIN {
    tot   = 0
    used  = 0
    us    = 0
    cnt   = 0
    mt    = 0
    model = ""
  }
  {
    tot  += $7
    used += $6
    us   += $5
    cnt  ++
    if ($10 > mt)    mt    = $10
    if (model == "") model = $3
  }
  END {
    free = tot - used
    avg  = cnt > 0 ? us   / cnt  : 0
    pct  = tot > 0 ? used / tot * 100 : 0
    printf "##XPUSMI##\t%s\t%d\t%d\t%d\t%.2f\t%.2f\t%d\t%s\t%d\n",
      lip, tot, used, free, pct, avg, mt, model, cnt
  }' "$tmp_actual_devices"
else
  printf "##XPUSMI##\t%s\t0\t0\t0\t0.00\t0.00\t0\tN/A\t0\n" "$_lip"
fi
EOF

bash /tmp/xpu_check.sh