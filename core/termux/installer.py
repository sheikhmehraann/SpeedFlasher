from typing import List


class TermuxInstaller:
    @staticmethod
    def generate_shell_script(
        device: str,
        codename: str,
        firmware_imgs: List[str],
        system_imgs: List[str],
        super_imgs: List[str],
        use_zstd: bool = False
    ) -> str:
        lines = [
            "#!/data/data/com.termux/files/usr/bin/bash",
            "set -e",
            'SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"',
            'cd "$SCRIPT_DIR"',
            "",
            'if ! command -v fastboot >/dev/null 2>&1; then',
            '    echo "[*] Installing android-tools in Termux..."',
            "    pkg update -y && pkg install -y android-tools",
            "fi",
            'FASTBOOT="fastboot"',
            "",
            'echo "=============================================="',
            'echo "      SpeedFlasher Fastboot Installer (Termux)"',
            'echo "=============================================="',
            f'echo "Target Device: {device} ({codename})"',
            'echo ""',
            '$FASTBOOT devices',
            'echo ""',
            'read -r -p "Format userdata after flashing? (y/n): " WIPE',
            'echo ""',
            'echo "Flashing firmware partitions..."',
        ]

        ext = ".img.zst" if use_zstd else ".img"
        for fw in firmware_imgs:
            lines.append(f'[ -f "{fw}{ext}" ] && $FASTBOOT flash "{fw}" "{fw}{ext}" || true')

        lines.append('echo ""')
        lines.append('echo "Flashing system bootchain partitions..."')
        for sys_part in system_imgs:
            lines.append(f'[ -f "{sys_part}{ext}" ] && $FASTBOOT flash "{sys_part}" "{sys_part}{ext}" || true')

        if super_imgs:
            lines.extend([
                'echo ""',
                'echo "Rebooting to fastbootd for dynamic partitions..."',
                '$FASTBOOT reboot fastboot || true',
                'sleep 5',
                'echo "Flashing dynamic partitions in fastbootd..."',
            ])
            for sp in super_imgs:
                lines.append(f'[ -f "{sp}{ext}" ] && $FASTBOOT flash "{sp}" "{sp}{ext}" || true')

        lines.extend([
            'echo ""',
            'if [ "$WIPE" = "y" ] || [ "$WIPE" = "Y" ]; then',
            '    echo "Wiping userdata..."',
            '    $FASTBOOT -w || true',
            "fi",
            'echo ""',
            'echo "Rebooting to system..."',
            '$FASTBOOT reboot',
            'echo "=============================================="',
            'echo "           Flashing Complete"',
            'echo "=============================================="',
        ])
        return "\n".join(lines)
