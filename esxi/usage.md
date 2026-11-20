export VCSA="vcsa.yourdomain.local"
export USER="administrator@vsphere.local"
export VCSA_PASS='YourPasswordHere'

# 1. Query a single host (accepts DNS name or IP)
python3 audit_esxi_gpus.py --target esxi-01.yourdomain.local

# 2. Query all hosts into the same nested JSON structure
python3 audit_esxi_gpus.py > esxi_gpu_inventory.json
