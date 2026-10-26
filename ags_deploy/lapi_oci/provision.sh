#!/usr/bin/env bash
# Provision Lapi on OCI Always Free, fully separate from Aegis.
# Run in OCI Cloud Shell (it is already signed in as you):
#   bash <(curl -fsSL https://raw.githubusercontent.com/Maniatramco/Lapi/lapi_sprint1/ags_deploy/lapi_oci/provision.sh)
#
# Creates ONLY new resources inside a new "lapi" compartment:
#   lapi-vcn (+ igw, public subnet), lapi-vm (A1.Flex 2 OCPU / 12 GB, 50 GB boot),
#   lapidb (Always Free Autonomous Database, TLS with IP allow-list).
# It never modifies, stops or deletes anything outside that compartment.
# Before creating anything it checks the whole tenancy stays within Always Free.
# Re-running is safe: existing Lapi resources are reused.
set -euo pipefail

T="${OCI_TENANCY:?Run this in OCI Cloud Shell}"
export OCI_CLI_REGION="${LAPI_REGION:-ap-mumbai-1}"
REPO=https://github.com/Maniatramco/Lapi.git
BRANCH=lapi_sprint1
OCPUS=2; MEM=12; BOOT=50
STATE="$HOME/.lapi"; mkdir -p "$STATE"; chmod 700 "$STATE"
exec > >(tee -a "$STATE/provision.log") 2>&1
say(){ printf '\nLAPI> %s\n' "$*"; }
die(){ printf '\nLAPI-STOP> %s\n' "$*"; exit 1; }
alive='select(."lifecycle-state" != "TERMINATED" and ."lifecycle-state" != "TERMINATING")'

# ---------------------------------------------------------------- 1. checks
say "1/7 Checking Always Free capacity across the tenancy (read-only)"
C=$(oci iam compartment list -c "$T" --all | jq -r '.data[]? | select(.name=="lapi" and ."lifecycle-state"=="ACTIVE") | .id' | head -1)

used_ocpu=0; used_mem=0; lapi_vm=""
for id in $(oci search resource structured-search --limit 200 \
    --query-text "query instance resources where lifecycleState != 'TERMINATED'" | jq -r '.data.items[]?.identifier'); do
  i=$(oci compute instance get --instance-id "$id")
  st=$(jq -r '.data."lifecycle-state"' <<<"$i"); [ "$st" = TERMINATING ] && continue
  name=$(jq -r '.data."display-name"' <<<"$i"); shape=$(jq -r .data.shape <<<"$i")
  if [ -n "$C" ] && [ "$(jq -r '.data."compartment-id"' <<<"$i")" = "$C" ] && [ "$name" = lapi-vm ]; then lapi_vm="$id"; continue; fi
  case "$shape" in
    VM.Standard.A1.Flex)
      used_ocpu=$(awk -v a="$used_ocpu" -v b="$(jq -r '.data."shape-config".ocpus' <<<"$i")" 'BEGIN{print a+b}')
      used_mem=$(awk -v a="$used_mem" -v b="$(jq -r '.data."shape-config"."memory-in-gbs"' <<<"$i")" 'BEGIN{print a+b}') ;;
    VM.Standard.E2.1.Micro) ;;
    *) die "Instance $name uses $shape, which is not Always Free. Not continuing." ;;
  esac
done
echo "Other A1 usage: $used_ocpu OCPU / $used_mem GB (Always Free total: 4 OCPU / 24 GB)"
if [ -z "$lapi_vm" ]; then
  awk -v o="$used_ocpu" -v m="$used_mem" -v O=$OCPUS -v M=$MEM 'BEGIN{exit !(o+O<=4 && m+M<=24)}' \
    || die "Adding $OCPUS OCPU / $MEM GB would exceed Always Free A1. Not continuing."
fi

used_gb=0
for row in $(oci search resource structured-search --limit 200 \
    --query-text "query bootvolume, volume resources where lifecycleState != 'TERMINATED'" \
    | jq -r '.data.items[]? | ."resource-type" + "|" + .identifier'); do
  type=${row%%|*}; id=${row#*|}
  if [ "$type" = BootVolume ]; then gb=$(oci bv boot-volume get --boot-volume-id "$id" | jq -r '.data."size-in-gbs"')
  else gb=$(oci bv volume get --volume-id "$id" | jq -r '.data."size-in-gbs"'); fi
  used_gb=$((used_gb + ${gb%.*}))
done
echo "Block storage in use: ${used_gb} GB (Always Free total: 200 GB)"
[ -n "$lapi_vm" ] || [ $((used_gb + BOOT)) -le 200 ] || die "A ${BOOT} GB boot volume would exceed the 200 GB Always Free storage. Not continuing."

free_adb=0; lapi_db=""
for id in $(oci search resource structured-search --limit 200 \
    --query-text "query autonomousdatabase resources where lifecycleState != 'TERMINATED'" | jq -r '.data.items[]?.identifier'); do
  d=$(oci db autonomous-database get --autonomous-database-id "$id")
  [ "$(jq -r '.data."lifecycle-state"' <<<"$d")" = TERMINATING ] && continue
  if [ -n "$C" ] && [ "$(jq -r '.data."compartment-id"' <<<"$d")" = "$C" ] && [ "$(jq -r '.data."db-name" | ascii_upcase' <<<"$d")" = LAPIDB ]; then lapi_db="$id"; continue; fi
  [ "$(jq -r '.data."is-free-tier"' <<<"$d")" = true ] || die "Database $(jq -r '.data."display-name"' <<<"$d") is not Always Free. Not continuing."
  free_adb=$((free_adb + 1))
done
echo "Other Always Free Autonomous Databases: $free_adb (limit 2)"
[ -n "$lapi_db" ] || [ "$free_adb" -lt 2 ] || die "Both Always Free database slots are in use. Not continuing."
echo "Capacity check passed."

# ---------------------------------------------------------- 2. compartment
say "2/7 Lapi compartment"
if [ -z "$C" ]; then
  C=$(oci iam compartment create -c "$T" --name lapi --description "Lapi app (separate from Aegis)" \
        --freeform-tags '{"app":"lapi"}' --wait-for-state ACTIVE | jq -r .data.id)
  echo "Created compartment lapi; waiting 60s for it to propagate"; sleep 60
else echo "Reusing compartment lapi"; fi

# -------------------------------------------------------------- 3. network
say "3/7 Lapi network"
V=$(oci network vcn list -c "$C" --display-name lapi-vcn | jq -r ".data[]? | $alive | .id" | head -1)
[ -n "$V" ] || V=$(oci network vcn create -c "$C" --display-name lapi-vcn --cidr-blocks '["10.60.0.0/16"]' \
                     --dns-label lapivcn --freeform-tags '{"app":"lapi"}' --wait-for-state AVAILABLE | jq -r .data.id)
IG=$(oci network internet-gateway list -c "$C" --vcn-id "$V" | jq -r '.data[0].id // empty')
[ -n "$IG" ] || IG=$(oci network internet-gateway create -c "$C" --vcn-id "$V" --is-enabled true \
                       --display-name lapi-igw --wait-for-state AVAILABLE | jq -r .data.id)
VJ=$(oci network vcn get --vcn-id "$V")
RT=$(jq -r '.data."default-route-table-id"' <<<"$VJ"); SL=$(jq -r '.data."default-security-list-id"' <<<"$VJ")
oci network route-table update --rt-id "$RT" --force \
  --route-rules "[{\"destination\":\"0.0.0.0/0\",\"destinationType\":\"CIDR_BLOCK\",\"networkEntityId\":\"$IG\"}]" >/dev/null
oci network security-list update --security-list-id "$SL" --force \
  --egress-security-rules '[{"destination":"0.0.0.0/0","protocol":"all","isStateless":false}]' \
  --ingress-security-rules '[
    {"source":"0.0.0.0/0","protocol":"6","isStateless":false,"tcpOptions":{"destinationPortRange":{"min":22,"max":22}}},
    {"source":"0.0.0.0/0","protocol":"6","isStateless":false,"tcpOptions":{"destinationPortRange":{"min":80,"max":80}}},
    {"source":"0.0.0.0/0","protocol":"1","isStateless":false,"icmpOptions":{"type":3,"code":4}}]' >/dev/null
SN=$(oci network subnet list -c "$C" --vcn-id "$V" | jq -r ".data[]? | $alive | .id" | head -1)
[ -n "$SN" ] || SN=$(oci network subnet create -c "$C" --vcn-id "$V" --display-name lapi-public --cidr-block 10.60.1.0/24 \
                       --dns-label pub --route-table-id "$RT" --security-list-ids "[\"$SL\"]" --wait-for-state AVAILABLE | jq -r .data.id)
echo "Network ready (lapi-vcn 10.60.0.0/16, ports 22 and 80 open)"

# ------------------------------------------------------------------- 4. VM
say "4/7 Lapi VM (A1.Flex $OCPUS OCPU / $MEM GB, ${BOOT} GB boot)"
[ -f "$STATE/lapi_ssh" ] || ssh-keygen -t ed25519 -N '' -C lapi -q -f "$STATE/lapi_ssh"
cat > "$STATE/cloud-init.sh" <<CI
#!/bin/bash
set -e
if [ ! -f /swapfile ]; then fallocate -l 4G /swapfile; chmod 600 /swapfile; mkswap /swapfile; swapon /swapfile; echo '/swapfile none swap sw 0 0' >> /etc/fstab; fi
apt-get update -y
DEBIAN_FRONTEND=noninteractive apt-get install -y docker.io docker-compose-v2 git curl
usermod -aG docker ubuntu
iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT
netfilter-persistent save || true
mkdir -p /opt/lapi/secrets
[ -d /opt/lapi/app ] || git clone --branch $BRANCH $REPO /opt/lapi/app
chown -R ubuntu:ubuntu /opt/lapi; chmod 700 /opt/lapi/secrets
touch /opt/lapi/cloud-init-done
CI
I="$lapi_vm"
if [ -z "$I" ]; then
  IMG=$(oci compute image list -c "$T" --operating-system "Canonical Ubuntu" --operating-system-version "24.04" \
          --shape VM.Standard.A1.Flex --sort-by TIMECREATED --sort-order DESC --limit 1 | jq -r '.data[0].id')
  for AD in $(oci iam availability-domain list -c "$T" | jq -r '.data[].name'); do
    if out=$(oci compute instance launch -c "$C" --availability-domain "$AD" --display-name lapi-vm \
          --shape VM.Standard.A1.Flex --shape-config "{\"ocpus\":$OCPUS,\"memoryInGBs\":$MEM}" \
          --image-id "$IMG" --subnet-id "$SN" --assign-public-ip true --boot-volume-size-in-gbs $BOOT \
          --ssh-authorized-keys-file "$STATE/lapi_ssh.pub" --user-data-file "$STATE/cloud-init.sh" \
          --freeform-tags '{"app":"lapi"}' --wait-for-state RUNNING 2>&1); then
      I=$(sed -n '/^{/,$p' <<<"$out" | jq -r .data.id); break
    else echo "$out" | tail -5; fi
  done
  [ -n "$I" ] || die "Could not create lapi-vm (often 'Out of host capacity' for free A1 in this region). Re-run later; nothing paid was created."
else echo "Reusing lapi-vm"; fi
VNIC=$(oci compute vnic-attachment list -c "$C" --instance-id "$I" | jq -r '.data[0]."vnic-id"')
IP=$(oci network vnic get --vnic-id "$VNIC" | jq -r '.data."public-ip"')
echo "$IP" > "$STATE/public_ip"; echo "lapi-vm public IP: $IP"

# ------------------------------------------------------------- 5. database
say "5/7 Lapi Always Free Autonomous Database (lapidb)"
DB="$lapi_db"
if [ -z "$DB" ]; then
  umask 077
  [ -s "$STATE/adb_admin_password" ] || printf 'Lp%s9x' "$(openssl rand -base64 48 | tr -dc A-Za-z0-9 | head -c 22)" > "$STATE/adb_admin_password"
  VER=$(oci db autonomous-db-version list -c "$T" --db-workload OLTP | jq -r '[.data[] | select(."is-free-tier-enabled") | .version] | sort | last')
  jq -n --arg c "$C" --arg pw "$(cat "$STATE/adb_admin_password")" --arg ip "$IP" --arg v "$VER" \
    '{compartmentId:$c, dbName:"lapidb", displayName:"lapidb", isFreeTier:true, dbWorkload:"OLTP", dbVersion:$v,
      adminPassword:$pw, isMtlsConnectionRequired:false, whitelistedIps:[$ip], freeformTags:{app:"lapi"}}' > "$STATE/adb-create.json"
  echo "Creating lapidb ($VER). This takes a few minutes."
  out=$(oci db autonomous-database create --from-json "file://$STATE/adb-create.json" --wait-for-state AVAILABLE --max-wait-seconds 1800 2>&1) || { rm -f "$STATE/adb-create.json"; echo "$out" | tail -8; die "Database creation failed."; }
  rm -f "$STATE/adb-create.json"
  DB=$(sed -n '/^{/,$p' <<<"$out" | jq -r .data.id)
  umask 022
else echo "Reusing lapidb"; fi
DSN=$(oci db autonomous-database get --autonomous-database-id "$DB" | jq -r '[.data."connection-strings".profiles[]
        | select(."consumer-group"=="LOW" and ."tls-authentication"=="SERVER" and .protocol=="TCPS")] | sort_by(."host-format" != "FQDN") | .[0].value')
[ -n "$DSN" ] && [ "$DSN" != null ] || die "lapidb has no TLS connection string yet."
printf 'lapidb_low = %s\n' "$DSN" > "$STATE/tnsnames.ora"
echo "lapidb ready (TLS, only $IP allowed)"

# --------------------------------------------------------------- 6. deploy
say "6/7 Waiting for lapi-vm to finish its first boot setup"
SSH=(ssh -i "$STATE/lapi_ssh" -o StrictHostKeyChecking=accept-new -o ConnectTimeout=10 -o ServerAliveInterval=30 "ubuntu@$IP")
for n in $(seq 60); do "${SSH[@]}" test -f /opt/lapi/cloud-init-done 2>/dev/null && break; sleep 20; done
"${SSH[@]}" test -f /opt/lapi/cloud-init-done || die "lapi-vm setup did not finish; re-run this script."
"${SSH[@]}" 'mkdir -p /opt/lapi/secrets/tns && cat > /opt/lapi/secrets/tns/tnsnames.ora' < "$STATE/tnsnames.ora"
"${SSH[@]}" 'umask 077; cat > /opt/lapi/secrets/adb_admin_password' < "$STATE/adb_admin_password"

say "7/7 Building and starting Lapi on lapi-vm"
"${SSH[@]}" "cd /opt/lapi/app && git pull -q --ff-only && PUBLIC_IP=$IP bash ags_deploy/lapi_oci/vm_up.sh"

say "DONE. Open http://$IP"
echo "First-admin bootstrap token (keep private): run  ssh -i ~/.lapi/lapi_ssh ubuntu@$IP cat /opt/lapi/secrets/bootstrap_token"
