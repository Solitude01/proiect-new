#!/usr/bin/env bash
# =============================================================
# 中心调度脚本：10.10.99.159 → 所有边缘节点 + 转换服务器
# =============================================================
set +e

# ─────────────────────────────────────────────
# 0. 节点配置
# ─────────────────────────────────────────────
declare -A IP_TO_GROUP=(
  ["10.65.233.21"]="广芯边缘"
  ["10.65.233.46"]="广芯边缘"
  ["10.20.7.165"]="无锡边缘"
  ["10.20.7.166"]="无锡边缘"
  ["10.30.4.33"]="南通边缘"
  ["10.30.4.34"]="南通边缘"
  ["10.10.99.78"]="深圳边缘"
  ["10.10.108.239"]="深圳转换服"
)

declare -A NODE_LABEL=(
  ["10.65.233.21"]="广芯边缘-1"
  ["10.65.233.46"]="广芯边缘-2"
  ["10.20.7.165"]="无锡边缘-1"
  ["10.20.7.166"]="无锡边缘-2"
  ["10.30.4.33"]="南通边缘-1"
  ["10.30.4.34"]="南通边缘-2"
  ["10.10.99.78"]="深圳边缘-1"
  ["10.10.108.239"]="深圳转换服"
)

ORDERED_IPS=(
  "10.65.233.21"
  "10.65.233.46"
  "10.20.7.165"
  "10.20.7.166"
  "10.30.4.33"
  "10.30.4.34"
  "10.10.99.78"
  "10.10.108.239"
)

# 总表输出顺序（用 | 分隔，避免中文空格歧义）
ORDERED_GROUPS_STR="广芯边缘|无锡边缘|南通边缘|深圳边缘|深圳转换服"

SSH_USER="${SSH_USER:-root}"
SSH_TIMEOUT="${SSH_TIMEOUT:-15}"
CMD_TIMEOUT="${CMD_TIMEOUT:-120}"
PARALLEL="${PARALLEL:-1}"
SCRIPT_PATH="/tmp/xpu_check.sh"

RESULT_DIR="$(mktemp -d /tmp/xpu_central_XXXXXX)"
trap 'rm -rf "$RESULT_DIR"' EXIT

# ─────────────────────────────────────────────
# 1. 内嵌边缘脚本
#    修复点：用 $() + cat 替代 read -r -d ''
# ─────────────────────────────────────────────
XPU_CHECK_SCRIPT=$(cat <<'SCRIPT_BODY'
#!/usr/bin/env bash
set +e
XPU_SMI_CMD="${XPU_SMI_CMD:-xpu_smi}"
section() { printf '\n===== %s =====\n' "$1"; }
tmp_nodes=$(mktemp); tmp_pods=$(mktemp)
tmp_actual_devices=$(mktemp); tmp_actual_procs=$(mktemp); tmp_actual_summary=$(mktemp)
trap 'rm -f "$tmp_nodes" "$tmp_pods" "$tmp_actual_devices" "$tmp_actual_procs" "$tmp_actual_summary"' EXIT

kubectl get nodes \
  -o custom-columns=NODE:.metadata.name,TYPE:.metadata.labels."tianniu\.baidu-int\.com/xpu-type",TOTAL:.status.capacity."baidu\.com/xpu-mem",INTERNAL_IP:.status.addresses[?\(@.type==\"InternalIP\"\)].address \
  --no-headers > "$tmp_nodes"

kubectl get pods -A \
  -o custom-columns=NS:.metadata.namespace,POD:.metadata.name,NODE:.spec.nodeName,XPUMEM:.spec.containers[*].resources.limits."baidu\.com/xpu-mem" \
  --no-headers > "$tmp_pods"

get_local_node_name() {
  local hn ips
  hn="$(hostname 2>/dev/null)"
  ips="$(hostname -I 2>/dev/null | tr ' ' '\n')"
  awk -v hn="$hn" -v ips="$ips" '
  BEGIN { split(ips,a,"\n"); for(i in a){ if(a[i]!="") lip[a[i]]=1 } }
  { if($1==hn || lip[$4]){ print $1; exit } }
  ' "$tmp_nodes"
}

parse_xpu_smi() {
  local node="$1"
  awk -v node="$node" '
  function trim(s){ gsub(/^[ \t]+|[ \t]+$/,"",s); return s }
  function num(s) { gsub(/^[ \t]+|[ \t]+$/,"",s); if(s~/[kK]$/){ sub(/[kK]$/,"",s); return s*1000 } if(s~/[mM]$/){ sub(/[mM]$/,"",s); return s*1000000 } if(s~/[gG]$/){ sub(/[gG]$/,"",s); return s*1000000000 } gsub(/[^0-9.]/,"",s); return s+0 }
  BEGIN{ mode=""; last_dev="" }
  $0~/^  DEVICES/ { mode="dev";  next }
  $0~/^  VIDEO/   { mode="video"; next }
  $0~/^  PROCESSES/{ mode="proc"; next }
  mode=="dev" && $0~/^\|[ \t]*[0-9]+[ \t]*\|/ {
    split($0,a,"|")
    dev_id=trim(a[2]); model=trim(a[4]); state=trim(a[7]); util=num(trim(a[8]))
    mem=trim(a[10]); power=num(trim(a[11])); temp=num(trim(a[12]))
    split(mem,m,"/"); used=num(m[1]); total=num(m[2]); free=total-used
    printf "%s\t%s\t%s\t%s\t%d\t%d\t%d\t%d\t%d\t%d\n",
      node,dev_id,model,state,util,used,total,free,power,temp >> ENVIRON["TMP_ACTUAL_DEVICES"]
    next
  }
  mode=="proc" && $0~/^\|/ {
    split($0,a,"|")
    dev_id=trim(a[2]); pid=trim(a[3]); streams=trim(a[4])
    l3=trim(a[5]); mem=trim(a[6]); cmd=trim(a[7])
    if(dev_id!="") last_dev=dev_id
    if(pid~/^[0-9]+$/)
      printf "%s\t%s\t%s\t%s\t%s\t%d\t%s\n",
        node,last_dev,pid,streams,l3,num(mem),cmd >> ENVIRON["TMP_ACTUAL_PROCS"]
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

awk -F'\t' '
{
  node=$1; util=$5+0; used=$6+0; total=$7+0; temp=$10+0
  used_sum[node]+=used; total_sum[node]+=total; util_sum[node]+=util; card_cnt[node]+=1
  if(temp>max_temp[node]) max_temp[node]=temp
}
END {
  for(n in total_sum){
    free=total_sum[n]-used_sum[n]
    usage=total_sum[n]>0 ? used_sum[n]/total_sum[n]*100 : 0
    avg_util=card_cnt[n]>0 ? util_sum[n]/card_cnt[n] : 0
    printf "%s\t%d\t%d\t%d\t%.2f\t%.2f\t%d\n",
      n,total_sum[n],used_sum[n],free,usage,avg_util,max_temp[n]
  }
}
' "$tmp_actual_devices" > "$tmp_actual_summary"

section "1) 节点 XPU 汇总：K8s 申请量 vs 本机实际消耗"
printf "%-18s %-15s %-15s %12s %12s %12s %12s %12s %12s %10s %10s %10s %12s\n" \
  "NODE" "INTERNAL_IP" "XPU_TYPE" "K8S_TOTAL" "K8S_USED" "K8S_FREE" \
  "REAL_TOTAL" "REAL_USED" "REAL_FREE" "REAL_USE" "AVG_UTIL" "MAX_TEMP" "REAL-K8S"

awk '
function add_mem(start,   i,j,arr,v,val,s) {
  s=0
  for(i=start;i<=NF;i++){
    split($i,arr,",")
    for(j in arr){ v=arr[j]; gsub(/^[ \t]+|[ \t]+$/,"",v); val=v+0; if(v~/[kK]$/)val*=1000; else if(v~/[mM]$/)val*=1000000; else if(v~/[gG]$/)val*=1000000000; if(val>0)s+=val }
  }
  return s
}
ARGIND==1 {
  if($1!="" && $3~/^[0-9]+$/){
    total[$1]=$3+0; type[$1]=$2; ip[$1]=$4
    if(type[$1]=="<none>"||type[$1]=="") type[$1]="-"
    if(ip[$1]=="<none>"||ip[$1]=="")     ip[$1]="-"
  }
  next
}
ARGIND==2 {
  node=$3
  if(node==""||node=="<none>") next
  mem=add_mem(4)
  if(mem>0) k8s_used[node]+=mem
  next
}
ARGIND==3 {
  real_total[$1]=$2+0; real_used[$1]=$3+0; real_free[$1]=$4+0
  real_usage[$1]=$5+0; avg_util[$1]=$6+0; max_temp[$1]=$7+0
  next
}
END {
  for(n in total){
    ku=k8s_used[n]+0; kf=total[n]-ku
    if(!(n in real_total)){
      printf "%-18s %-15s %-15s %12d %12d %12d %12s %12s %12s %10s %10s %10s %12s\n",
        n,ip[n],type[n],total[n],ku,kf,"N/A","N/A","N/A","N/A","N/A","N/A","N/A"
      continue
    }
    diff=real_used[n]-ku
    printf "%-18s %-15s %-15s %12d %12d %12d %12d %12d %12d %9.2f%% %9.2f%% %9dC %12d\n",
      n,ip[n],type[n],total[n],ku,kf,
      real_total[n],real_used[n],real_free[n],real_usage[n],avg_util[n],max_temp[n],diff
  }
}
' "$tmp_nodes" "$tmp_pods" "$tmp_actual_summary" | sort -k1,1

section "2) 本机单卡实际消耗明细：来自 xpu_smi"
printf "%-18s %6s %-8s %-6s %8s %12s %12s %12s %10s %8s\n" \
  "NODE" "DevID" "Model" "State" "UseRate" "USED_MB" "TOTAL_MB" "FREE_MB" "Power(W)" "Temp"
if [ -s "$tmp_actual_devices" ]; then
  awk -F'\t' '{
    printf "%-18s %6s %-8s %-6s %7d%% %12d %12d %12d %10d %7dC\n",
      $1,$2,$3,$4,$5,$6,$7,$8,$9,$10
  }' "$tmp_actual_devices" | sort -k1,1 -k2,2n
  awk -F'\t' '{
    used+=$6; total+=$7; free+=$8; power+=$9; util+=$5; cnt++
  }
  END {
    if(cnt>0)
      printf "%-18s %6s %-8s %-6s %6.1f%% %12d %12d %12d %10d %7s\n",
        "[合计]", "", "", "", util/cnt, used, total, free, power, ""
  }' "$tmp_actual_devices"
else
  echo "本机未采集到 xpu_smi 数据"
fi

section "3) 本机 XPU 进程实际消耗明细：来自 xpu_smi"
printf "%-18s %6s %10s %8s %10s %10s %-20s\n" \
  "NODE" "DevID" "PID" "Streams" "L3" "MEM_MB" "Command"
if [ -s "$tmp_actual_procs" ]; then
  awk -F'\t' '{
    printf "%-18s %6s %10s %8s %10s %10d %-20s\n",
      $1,$2,$3,$4,$5,$6,$7
  }' "$tmp_actual_procs" | sort -k1,1 -k2,2n -k6,6nr
  awk -F'\t' '{
    mem+=$6; cnt++
  }
  END {
    if(cnt>0)
      printf "%-18s %6s %10d %8s %10s %10d %-20s\n",
        "[合计]", "", cnt, "", "", mem, "(进程数/总内存MiB)"
  }' "$tmp_actual_procs"
else
  echo "本机未采集到 XPU 进程数据"
fi

section "4) XPU Pod 申请明细：来自 K8s limits"
printf "%-12s %-48s %-18s %12s\n" "空间" "Pod" "节点" "申请MiB"
awk '
function add_mem(start,   i,j,arr,v,val,s) {
  s=0
  for(i=start;i<=NF;i++){
    split($i,arr,",")
    for(j in arr){ v=arr[j]; gsub(/^[ \t]+|[ \t]+$/,"",v); val=v+0; if(v~/[kK]$/)val*=1000; else if(v~/[mM]$/)val*=1000000; else if(v~/[gG]$/)val*=1000000000; if(val>0)s+=val }
  }
  return s
}
{
  if($1==""||$1=="<none>") next
  mem=add_mem(4)
  if(mem>0) printf "%-12s %-48s %-18s %12d\n",$1,$2,$3,mem
}
' "$tmp_pods" | sort -k3,3 -k4,4nr

awk '
function add_mem(start,   i,j,arr,v,val,s) {
  s=0
  for(i=start;i<=NF;i++){
    split($i,arr,",")
    for(j in arr){ v=arr[j]; gsub(/^[ \t]+|[ \t]+$/,"",v); val=v+0; if(v~/[kK]$/)val*=1000; else if(v~/[mM]$/)val*=1000000; else if(v~/[gG]$/)val*=1000000000; if(val>0)s+=val }
  }
  return s
}
{
  if($1==""||$1=="<none>") next
  mem=add_mem(4)
  if(mem>0){
    pod_cnt++
    pod_mem+=mem
    ns_set[$1]=1
    if($3!=""&&$3!="<none>") node_set[$3]=1
  }
}
END {
  for(n in ns_set) ns_cnt++
  for(n in node_set) node_cnt++
  printf "%-12s %-48s %-18s %12d\n",
    "[合计]", "(Pod:" pod_cnt " 空间:" ns_cnt " 节点:" node_cnt ")", "", pod_mem
}
' "$tmp_pods"

section "5) Deployment 副本情况"
printf "%-10s %-40s %10s %10s\n" "空间" "名称" "期望副本" "可用副本"
kubectl get deployments -n default \
  -o custom-columns=NAME:.metadata.name,DESIRED:.spec.replicas,AVAILABLE:.status.availableReplicas \
  --no-headers | awk '
$1~/^ep-/ || $1=="tn-controller-manager-ep-package" {
  desired=$2; available=$3
  if(desired=="<none>"||desired=="")   desired=0
  if(available=="<none>"||available=="") available=0
  printf "%-10s %-40s %10s %10s\n","default",$1,desired,available
  cnt++
  tot_desired+=desired
  tot_available+=available
}
END {
  if(cnt>0)
    printf "%-10s %-40s %10d %10d\n","[合计]","(共" cnt "个Deployment)",tot_desired,tot_available
}'

section "6) 结构化摘要（中心端聚合专用）"
_lip=$(hostname -I 2>/dev/null | awk '{print $1}')
if [ -s "$tmp_actual_devices" ]; then
  awk -F'\t' -v lip="$_lip" '
  BEGIN{ tot=0; used=0; us=0; cnt=0; mt=0; model="" }
  {
    tot+=($7+0); used+=($6+0); us+=($5+0); cnt++
    if(($10+0)>mt) mt=($10+0)
    if(model=="") model=$3
  }
  END{
    free=tot-used
    avg = cnt>0  ? us/cnt    : 0
    pct = tot>0  ? used/tot*100 : 0
    printf "##XPUSMI##\t%s\t%d\t%d\t%d\t%.2f\t%.2f\t%d\t%s\t%d\n",
      lip,tot,used,free,pct,avg,mt,model,cnt
  }' "$tmp_actual_devices"
else
  printf "##XPUSMI##\t%s\t0\t0\t0\t0.00\t0.00\t0\tN/A\t0\n" "$_lip"
fi
SCRIPT_BODY
)

# ─────────────────────────────────────────────
# 2. 工具函数
# ─────────────────────────────────────────────
COLOR_RESET="\033[0m"
COLOR_CYAN="\033[1;36m"
COLOR_GREEN="\033[1;32m"
COLOR_RED="\033[1;31m"
COLOR_YELLOW="\033[1;33m"
COLOR_BOLD="\033[1m"

banner() {
  printf "\n${COLOR_CYAN}╔══════════════════════════════════════════════════════════╗${COLOR_RESET}\n"
  printf   "${COLOR_CYAN}║  %-56s║${COLOR_RESET}\n" "  $1"
  printf   "${COLOR_CYAN}╚══════════════════════════════════════════════════════════╝${COLOR_RESET}\n"
}
log_ok()   { printf "${COLOR_GREEN}  [✔] %s${COLOR_RESET}\n" "$*"; }
log_err()  { printf "${COLOR_RED}  [✘] %s${COLOR_RESET}\n"   "$*"; }
log_warn() { printf "${COLOR_YELLOW}  [!] %s${COLOR_RESET}\n"  "$*"; }

# ─────────────────────────────────────────────
# 2.4 从中心端 MySQL 拉取 endpoint→模型中文名映射
#    数据来源: windmill.deploy_endpoint_job + endpoint + model
#    输出: ep_id | 服务名 | 模型英文名 | 模型中文名 | gpu | vgpu | cpu | compute
# ─────────────────────────────────────────────
query_model_lookup() {
  local lookup_file="$1"
  kubectl exec -n middleware xdbmysql57-0 -- \
    /mysql/bin/mysql --defaults-file=/mysql/etc/user.root.cnf \
    -D windmill --default-character-set=utf8mb4 -N -e \
    "SELECT DISTINCT SUBSTRING_INDEX(e.uri, '/', -1), e.local_name, m.local_name, m.display_name, JSON_UNQUOTE(JSON_EXTRACT(m.prefer_model_server_parameters, '$.resource.gpu')), JSON_UNQUOTE(JSON_EXTRACT(m.prefer_model_server_parameters, '$.resource.vgpuEnabled')), JSON_UNQUOTE(JSON_EXTRACT(m.prefer_model_server_parameters, '$.resource.limits.cpu')), SUBSTRING_INDEX(dej.endpoint_compute_name, '/', -1) FROM deploy_endpoint_job dej JOIN endpoint e ON e.local_name = dej.endpoint_name JOIN model m ON m.local_name = SUBSTRING_INDEX(SUBSTRING_INDEX(dej.artifact_name, 'models/', -1), '/versions', 1) WHERE m.local_name NOT LIKE '%pre%' AND m.local_name NOT LIKE '%post%' ORDER BY SUBSTRING_INDEX(e.uri, '/', -1);" \
    2>/dev/null > "$lookup_file"
  return $?
}

lookup_model() {
  local ep_id="$1"
  local lookup_file="$2"
  awk -F'\t' -v id="$ep_id" '$1 == id { print $0; exit }' "$lookup_file"
}

# ─────────────────────────────────────────────
# 2.5 从节点 .out 文件中提取指定 section 的内容
# ─────────────────────────────────────────────
extract_section_lines() {
  local out_file="$1"
  local sec_num="$2"
  [ -f "$out_file" ] || return
  awk -v sn="$sec_num" '
  /^===== / {
    if (in_target) exit
    n = $2; gsub(/[^0-9]/, "", n)
    if (n+0 == sn+0) { in_target=1; next }
  }
  in_target { print }
  ' "$out_file"
}

# ─────────────────────────────────────────────
# 3. 单台节点采集
# ─────────────────────────────────────────────
collect_node() {
  local ip="$1"
  local label="${NODE_LABEL[$ip]:-$ip}"
  local out_file="${RESULT_DIR}/${ip}.out"
  local err_file="${RESULT_DIR}/${ip}.err"
  local status_file="${RESULT_DIR}/${ip}.status"

  timeout "$CMD_TIMEOUT" ssh \
    -o StrictHostKeyChecking=no \
    -o ConnectTimeout="$SSH_TIMEOUT" \
    -o BatchMode=yes \
    "${SSH_USER}@${ip}" \
    "cat > ${SCRIPT_PATH} && bash ${SCRIPT_PATH}" \
    <<< "$XPU_CHECK_SCRIPT" \
    > "$out_file" 2> "$err_file"

  local rc=$?
  echo "$rc" > "$status_file"

  if   [ "$rc" -eq 0 ];   then log_ok  "[$label] $ip — 采集完成"
  elif [ "$rc" -eq 124 ]; then log_err "[$label] $ip — 超时（${CMD_TIMEOUT}s）"
  else                          log_err "[$label] $ip — 失败 (rc=$rc)：$(head -3 "$err_file")"
  fi
}

# ─────────────────────────────────────────────
# 4. 解析 ##XPUSMI## 行
#    修复点：不用管道子 shell，直接 awk 遍历所有 .out 文件
# ─────────────────────────────────────────────
SUMMARY_TSV="${RESULT_DIR}/summary.tsv"

parse_all_xpusmi() {
  # 表头
  printf "GROUP\tIP\tTOTAL\tUSED\tFREE\tUSAGE\tAVGUTIL\tMAXTEMP\tMODEL\tDEVCNT\n" \
    > "$SUMMARY_TSV"

  for ip in "${ORDERED_IPS[@]}"; do
    local out_file="${RESULT_DIR}/${ip}.out"
    local group="${IP_TO_GROUP[$ip]:-未知}"
    [ -f "$out_file" ] || continue

    local line
    line=$(grep '^##XPUSMI##' "$out_file" | head -1)
    [ -z "$line" ] && continue

    # 按 tab 切分（避免 IFS 子 shell 问题）
    local _tag _ip total used free usage avgutil maxtemp model devcnt
    IFS=$'\t' read -r _tag _ip total used free usage avgutil maxtemp model devcnt <<< "$line"

    printf "%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n" \
      "$group" "${_ip:-$ip}" "${total:-0}" "${used:-0}" "${free:-0}" \
      "${usage:-0}" "${avgutil:-0}" "${maxtemp:-0}" "${model:-N/A}" "${devcnt:-0}" \
      >> "$SUMMARY_TSV"
  done
}

# ─────────────────────────────────────────────
# 5. 总表：按边缘节点维度聚合
#    修复点：组名用 | 分隔传给 awk，避免中文 split 歧义
# ─────────────────────────────────────────────
print_total_table() {
  banner "全局边缘节点 XPU 资源总表"

  printf "${COLOR_BOLD}%-16s %8s %14s %14s %14s %10s %10s %10s %-10s${COLOR_RESET}\n" \
    "边缘节点" "服务器数" "总显存(MB)" "已用(MB)" "空闲(MB)" "使用率" "平均利用" "最高温度" "型号"
  printf "%-16s %8s %14s %14s %14s %10s %10s %10s %-10s\n" \
    "──────────────" "────────" "──────────────" "──────────────" "──────────────" \
    "──────────" "──────────" "──────────" "────────"

  awk -F'\t' -v ordered="$ORDERED_GROUPS_STR" '
  NR==1 { next }
  {
    g=$1; total=$3+0; used=$4+0; avgutil=$7+0; maxtemp=$8+0; model=$9; devcnt=$10+0
    grp_total[g]  += total
    grp_used[g]   += used
    grp_free[g]   += (total - used)
    grp_util[g]   += avgutil
    grp_srvs[g]   += 1
    if(maxtemp > grp_maxtemp[g]) grp_maxtemp[g] = maxtemp
    if(grp_model[g]=="") grp_model[g] = model
  }
  END {
    # 按 | 分隔保证中文顺序正确
    n = split(ordered, o, "|")
    total_all=0; used_all=0; free_all=0; srvs_all=0

    for(i=1; i<=n; i++){
      g = o[i]
      if(!(g in grp_total)){
        printf "%-16s %8s %14s %14s %14s %10s %10s %10s %-10s\n",
          g,"-","N/A","N/A","N/A","N/A","N/A","N/A","N/A"
        continue
      }
      pct = grp_total[g]>0 ? grp_used[g]/grp_total[g]*100 : 0
      avg = grp_srvs[g]>0  ? grp_util[g]/grp_srvs[g]      : 0
      free = grp_free[g]

      printf "%-16s %8d %14d %14d %14d %9.2f%% %9.2f%% %8d°C %-10s\n",
        g, grp_srvs[g], grp_total[g], grp_used[g], free,
        pct, avg, grp_maxtemp[g], grp_model[g]

      total_all += grp_total[g]
      used_all  += grp_used[g]
      free_all  += free
      srvs_all  += grp_srvs[g]
    }

    # 合计行
    printf "%-16s %8s %14s %14s %14s %10s %10s %10s %-10s\n",
      "────────────────","──────","────────────","────────────","────────────",
      "────────","────────","────────","────────"
    pct_all = total_all>0 ? used_all/total_all*100 : 0
    printf "%-16s %8d %14d %14d %14d %9.2f%%\n",
      "【合计】", srvs_all, total_all, used_all, free_all, pct_all
  }
  ' "$SUMMARY_TSV"
}

# ─────────────────────────────────────────────
# 5.5 按边缘节点组维度展示详细数据
# ─────────────────────────────────────────────
print_group_details() {
  local processed_groups ip group label out_file status_file rc
  local svr_count ok_count first_ok_ip sec_content first_flag
  local -a group_ips
  local inner_ip inner_rc

  processed_groups="|"

  for ip in "${ORDERED_IPS[@]}"; do
    group="${IP_TO_GROUP[$ip]:-未知}"
    [[ "$processed_groups" == *"|$group|"* ]] && continue
    processed_groups="${processed_groups}${group}|"

    # 收集组内所有 IP，统计成功数
    group_ips=()
    svr_count=0; ok_count=0; first_ok_ip=""
    for inner_ip in "${ORDERED_IPS[@]}"; do
      if [ "${IP_TO_GROUP[$inner_ip]}" = "$group" ]; then
        group_ips+=("$inner_ip")
        svr_count=$((svr_count + 1))
        inner_rc=1
        [ -f "${RESULT_DIR}/${inner_ip}.status" ] && inner_rc=$(cat "${RESULT_DIR}/${inner_ip}.status")
        if [ "$inner_rc" -eq 0 ]; then
          ok_count=$((ok_count + 1))
          [ -z "$first_ok_ip" ] && first_ok_ip="$inner_ip"
        fi
      fi
    done

    # ── 组标题 ──
    printf "\n${COLOR_YELLOW}▶▶▶  %s (%d 台服务器, %d 台在线)  ◀◀◀${COLOR_RESET}\n" \
      "$group" "$svr_count" "$ok_count"

    if [ "$ok_count" -eq 0 ]; then
      printf "  ${COLOR_RED}该组所有节点均采集失败，无可用数据${COLOR_RESET}\n"
      continue
    fi

    # ── 1) 节点 XPU 汇总 (多节点合并，K8s列取首份，REAL列从对应物理机填充) ──
    printf "\n${COLOR_CYAN}  ═══ 1) 节点 XPU 汇总：K8s 申请量 vs 实际消耗 ═══${COLOR_RESET}\n"

    local sec1_tmp sec1_count
    sec1_tmp=$(mktemp)
    sec1_count=0
    for inner_ip in "${group_ips[@]}"; do
      out_file="${RESULT_DIR}/${inner_ip}.out"
      inner_rc=1
      [ -f "${RESULT_DIR}/${inner_ip}.status" ] && inner_rc=$(cat "${RESULT_DIR}/${inner_ip}.status")
      [ "$inner_rc" -ne 0 ] && continue

      sec_content=$(extract_section_lines "$out_file" 1)
      if [ -n "$sec_content" ]; then
        printf '%s\n' "$sec_content" >> "$sec1_tmp"
        sec1_count=$((sec1_count + 1))
      fi
    done

    if [ "$sec1_count" -gt 0 ]; then
      printf "  ${COLOR_GREEN}(合并 %d 个节点数据)${COLOR_RESET}\n" "$sec1_count"
      awk '
      BEGIN { header=""; idx=0 }
      {
        if ($1 == "NODE") { if (header=="") header=$0; next }
        if ($0 ~ /^[ \t]*$/) next
        node = $1
        if (!(node in seen)) {
          seen[node] = 1
          order[++idx] = node
          rows[node] = $0
        } else if ($7 != "N/A") {
          rows[node] = $0
        }
      }
      END {
        print header
        for (i=1; i<=idx; i++) print rows[order[i]]
      }
      ' "$sec1_tmp" | sed 's/^/  │  /'
    else
      printf "  ${COLOR_RED}无可用数据${COLOR_RESET}\n"
    fi
    rm -f "$sec1_tmp"

    # ── 2) 单卡实际消耗明细 (合并，去重表头) ──
    printf "\n${COLOR_CYAN}  ═══ 2) 单卡实际消耗明细：来自 xpu_smi ═══${COLOR_RESET}\n"
    first_flag=1
    for inner_ip in "${group_ips[@]}"; do
      label="${NODE_LABEL[$inner_ip]:-$inner_ip}"
      out_file="${RESULT_DIR}/${inner_ip}.out"
      inner_rc=1
      [ -f "${RESULT_DIR}/${inner_ip}.status" ] && inner_rc=$(cat "${RESULT_DIR}/${inner_ip}.status")
      [ "$inner_rc" -ne 0 ] && continue

      sec_content=$(extract_section_lines "$out_file" 2)
      if [ -n "$sec_content" ]; then
        printf "  ${COLOR_GREEN}[%s]${COLOR_RESET}\n" "$label"
        if [ "$first_flag" -eq 1 ]; then
          printf '%s\n' "$sec_content" | sed 's/^/  │  /'
          first_flag=0
        else
          printf '%s\n' "$sec_content" | tail -n +2 | sed 's/^/  │  /'
        fi
      fi
    done
    [ "$first_flag" -eq 1 ] && printf "  ${COLOR_RED}无可用数据${COLOR_RESET}\n"

    # ── 3) XPU 进程实际消耗明细 (合并，去重表头) ──
    printf "\n${COLOR_CYAN}  ═══ 3) XPU 进程实际消耗明细：来自 xpu_smi ═══${COLOR_RESET}\n"
    first_flag=1
    for inner_ip in "${group_ips[@]}"; do
      label="${NODE_LABEL[$inner_ip]:-$inner_ip}"
      out_file="${RESULT_DIR}/${inner_ip}.out"
      inner_rc=1
      [ -f "${RESULT_DIR}/${inner_ip}.status" ] && inner_rc=$(cat "${RESULT_DIR}/${inner_ip}.status")
      [ "$inner_rc" -ne 0 ] && continue

      sec_content=$(extract_section_lines "$out_file" 3)
      if [ -n "$sec_content" ]; then
        printf "  ${COLOR_GREEN}[%s]${COLOR_RESET}\n" "$label"
        if [ "$first_flag" -eq 1 ]; then
          printf '%s\n' "$sec_content" | sed 's/^/  │  /'
          first_flag=0
        else
          printf '%s\n' "$sec_content" | tail -n +2 | sed 's/^/  │  /'
        fi
      fi
    done
    [ "$first_flag" -eq 1 ] && printf "  ${COLOR_RED}无可用数据${COLOR_RESET}\n"

    # ── 4) XPU Pod 申请明细 (去重，同组只取第一个成功节点) ──
    printf "\n${COLOR_CYAN}  ═══ 4) XPU Pod 申请明细：来自 K8s limits (已去重) ═══${COLOR_RESET}\n"
    if [ -n "$first_ok_ip" ]; then
      label="${NODE_LABEL[$first_ok_ip]:-$first_ok_ip}"
      out_file="${RESULT_DIR}/${first_ok_ip}.out"
      printf "  ${COLOR_GREEN}(数据来源: %s / %s)${COLOR_RESET}\n" "$label" "$first_ok_ip"
      extract_section_lines "$out_file" 4 | sed 's/^/  │  /'
    else
      printf "  ${COLOR_RED}无可用数据${COLOR_RESET}\n"
    fi

    # ── 5) Deployment 副本情况 (去重，同组只取第一个成功节点) ──
    printf "\n${COLOR_CYAN}  ═══ 5) Deployment 副本情况 (已去重) ═══${COLOR_RESET}\n"
    if [ -n "$first_ok_ip" ]; then
      label="${NODE_LABEL[$first_ok_ip]:-$first_ok_ip}"
      out_file="${RESULT_DIR}/${first_ok_ip}.out"
      printf "  ${COLOR_GREEN}(数据来源: %s / %s)${COLOR_RESET}\n" "$label" "$first_ok_ip"
      extract_section_lines "$out_file" 5 | sed 's/^/  │  /'
    else
      printf "  ${COLOR_RED}无可用数据${COLOR_RESET}\n"
    fi

    # ── 7) 服务-模型映射表（从 MySQL 拉取）──
    printf "\n${COLOR_CYAN}  ═══ 7) 服务-模型映射表 ═══${COLOR_RESET}\n"

    # 收集该组所有 Deployment 名称 (ep-xxxxxxxx)
    local dep_names
    dep_names=$(for inner_ip2 in "${group_ips[@]}"; do
      out_file2="${RESULT_DIR}/${inner_ip2}.out"
      inner_rc2=1
      [ -f "${RESULT_DIR}/${inner_ip2}.status" ] && inner_rc2=$(cat "${RESULT_DIR}/${inner_ip2}.status")
      [ "$inner_rc2" -ne 0 ] && continue
      extract_section_lines "$out_file2" 5 | awk 'NR>1 && $2 ~ /^ep-/ { print $2 }'
    done | sort -u)

    if [ -n "$dep_names" ] && [ -s "$MODEL_LOOKUP_FILE" ]; then
      printf "  %-14s %-40s %-36s %-24s %6s %6s %5s %-10s\n" \
        "Endpoint" "服务名" "模型英文名" "模型中文名" "GPU" "vGPU" "CPU" "Compute"
      printf "  %-14s %-40s %-36s %-24s %6s %6s %5s %-10s\n" \
        "────────────" "──────────────────────────────────────" "──────────────────────────────────" "──────────────────────" "──────" "──────" "─────" "────────"

      local ep_id found
      while IFS= read -r ep_id; do
        found=$(lookup_model "$ep_id" "$MODEL_LOOKUP_FILE")
        if [ -n "$found" ]; then
          local _eid _svc _men _mcn _gpu _vgpu _cpu _comp
          IFS=$'\t' read -r _eid _svc _men _mcn _gpu _vgpu _cpu _comp <<< "$found"
          printf "  %-14s %-40s %-36s %-24s %6s %6s %5s %-10s\n" \
            "$_eid" "$_svc" "$_men" "$_mcn" "$_gpu" "$_vgpu" "$_cpu" "$_comp"
        else
          printf "  %-14s ${COLOR_YELLOW}%-40s${COLOR_RESET}\n" "$ep_id" "(未关联模型)"
        fi
      done <<< "$dep_names"
    elif [ -z "$dep_names" ]; then
      printf "  ${COLOR_RED}该组无 deployment 数据${COLOR_RESET}\n"
    else
      printf "  ${COLOR_YELLOW}模型映射缓存不可用 (MySQL 查询失败)，跳过映射展示${COLOR_RESET}\n"
    fi
  done
}

# ─────────────────────────────────────────────
# 6. 主流程
# ─────────────────────────────────────────────
banner "XPU 中心巡检  $(date '+%Y-%m-%d %H:%M:%S')"
printf "  中心节点：10.10.99.159\n"
printf "  目标节点：%d 台\n\n" "${#ORDERED_IPS[@]}"

if [ "$PARALLEL" -eq 1 ]; then
  log_warn "并行模式：同时连接所有节点..."
  pids=()
  for ip in "${ORDERED_IPS[@]}"; do
    collect_node "$ip" &
    pids+=($!)
  done
  for pid in "${pids[@]}"; do wait "$pid"; done
else
  log_warn "串行模式：逐台连接..."
  for ip in "${ORDERED_IPS[@]}"; do collect_node "$ip"; done
fi

# 并行结束后再解析（保证所有 .out 都已落盘）
parse_all_xpusmi

# 构建模型名映射缓存（从 MySQL 拉取 endpoint→模型中文名）
MODEL_LOOKUP_FILE="${RESULT_DIR}/model_lookup.tsv"
if query_model_lookup "$MODEL_LOOKUP_FILE"; then
  log_ok "模型映射缓存已就绪 ($(wc -l < "$MODEL_LOOKUP_FILE") 条)"
else
  log_warn "MySQL 模型映射查询失败，将跳过服务-模型映射展示"
  rm -f "$MODEL_LOOKUP_FILE"
fi

# 总表优先展示
print_total_table

# ─────────────────────────────────────────────
# 7. 按边缘节点组维度展示详细数据
# ─────────────────────────────────────────────
print_group_details

# ─────────────────────────────────────────────
# 8. 采集状态汇总
# ─────────────────────────────────────────────
banner "采集状态汇总"
printf "%-12s %-18s %-10s %s\n" "节点名" "IP" "状态" "分组"
printf "%-12s %-18s %-10s %s\n" "──────────" "──────────────────" "────────" "────────"
for ip in "${ORDERED_IPS[@]}"; do
  label="${NODE_LABEL[$ip]:-$ip}"
  group="${IP_TO_GROUP[$ip]:-未知}"
  status_file="${RESULT_DIR}/${ip}.status"
  rc=1; [ -f "$status_file" ] && rc=$(cat "$status_file")
  if [ "$rc" -eq 0 ]; then
    printf "%-12s %-18s ${COLOR_GREEN}✔ 成功  ${COLOR_RESET} %s\n" "$label" "$ip" "$group"
  else
    printf "%-12s %-18s ${COLOR_RED}✘ 失败  ${COLOR_RESET} %s\n" "$label" "$ip" "$group"
  fi
done

printf "\n巡检结束  $(date '+%Y-%m-%d %H:%M:%S')\n"
