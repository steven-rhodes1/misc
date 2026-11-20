import argparse
import json
import os
import ssl
import sys
from pyVim.connect import SmartConnect, Disconnect
from pyVmomi import vim


def get_args():
    parser = argparse.ArgumentParser(description="Audit ESXi GPU attachments on VCSA 8")
    parser.add_argument(
        "--target",
        help="Optional single ESXi host DNS name or IP (omit to scan all hosts)",
        default=None,
    )
    return parser.parse_args()


def main():
    args = get_args()

    vcsa_host = os.environ["VCSA"]
    vcsa_user = os.environ["USER"]
    vcsa_pass = os.environ["VCSA_PASS"]

    context = ssl._create_unverified_context()
    si = SmartConnect(
        host=vcsa_host,
        user=vcsa_user,
        pwd=vcsa_pass,
        sslContext=context,
    )
    content = si.RetrieveContent()

    # Build target host list: single host if --target is set, otherwise all hosts
    if args.target:
        host_obj = content.searchIndex.FindByDnsName(dnsName=args.target, vmSearch=False)
        if not host_obj:
            host_obj = content.searchIndex.FindByIp(ip=args.target, vmSearch=False)
        if not host_obj:
            print(f"Error: Host '{args.target}' not found in vCenter.", file=sys.stderr)
            Disconnect(si)
            sys.exit(1)
        hosts_to_check = [host_obj]
    else:
        container = content.viewManager.CreateContainerView(
            content.rootFolder, [vim.HostSystem], True
        )
        hosts_to_check = list(container.view)
        container.Destroy()

    # Unified loop building a nested dictionary for 1 or N hosts
    hosts_inventory = {}

    for host in hosts_to_check:
        cfg = host.config
        graphics_cfg = getattr(cfg, "graphicsConfig", None)

        passthru_devices = [
            pci.id
            for pci in (getattr(cfg, "pciPassthruInfo", None) or [])
            if pci.passthruActive
        ]

        nvidia_devices = [
            {
                "device_name": gfx.deviceName,
                "pci_id": gfx.pciId,
                "graphics_type": getattr(gfx, "graphicsType", None),
                "attached_vms": [vm.name for vm in (gfx.vm or [])],
            }
            for gfx in (getattr(cfg, "graphicsInfo", None) or [])
            if "NVIDIA" in gfx.deviceName.upper()
        ]

        vgpu_profiles = list(getattr(cfg, "sharedPassthruGpuTypes", None) or [])
        host_gfx_type = getattr(graphics_cfg, "hostDefaultGraphicsType", None)
        vgpu_mode = getattr(graphics_cfg, "sharedPassthruGpuAssignmentPolicy", None)

        # Determine effective GPU attachment mode
        if host_gfx_type == "sharedDirect" or vgpu_profiles:
            mode = "nvidia_vgpu"
        elif passthru_devices:
            mode = "pcie_passthrough"
        elif nvidia_devices:
            mode = "unassigned_gpu"
        else:
            mode = "no_gpu"

        hosts_inventory[host.name] = {
            "mode": mode,
            "graphics_type": host_gfx_type,
            "vgpu_mode": vgpu_mode,
            "vgpu_profiles": vgpu_profiles,
            "passthru_pci_ids": passthru_devices,
            "nvidia_devices": nvidia_devices,
        }

    Disconnect(si)

    # Output structured JSON
    print(json.dumps(hosts_inventory, indent=2))


if __name__ == "__main__":
    main()
