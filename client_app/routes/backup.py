"""Backup export and import."""

import os
import shutil
import sys
import zipfile

from flask import flash, redirect, render_template, request, send_file, url_for

import storage


def register_backup_routes(app, helpers):
    exe_dir = helpers["exe_dir"]

    @app.route("/backup/export", methods=["POST"])
    def backup_export():
        from app_platform import is_desktop
        from app_platform.backup import BackupExportError, build_backup_zip, export_backup_with_dialog

        if is_desktop() or sys.platform == "win32":
            try:
                path = export_backup_with_dialog(exe_dir())
                if path:
                    flash(f"Backup saved to {path}", "success")
                    from account import telemetry

                    telemetry.send_event("backup_export")
                else:
                    flash("Backup cancelled.", "info")
            except BackupExportError as exc:
                flash(str(exc), "error")
            return redirect(url_for("backup_import"))

        buf, stamp = build_backup_zip(exe_dir())
        return send_file(
            buf,
            mimetype="application/zip",
            as_attachment=True,
            download_name=f"FrogsWork-backup_{stamp}.zip",
        )

    @app.route("/backup/import", methods=["GET", "POST"])
    def backup_import():
        if request.method == "POST":
            file = request.files.get("backup_file")
            if not file:
                return render_template("backup_import.html", error="Choose a backup ZIP file.")
            data_path = storage.get_data_path()
            pdf_dir = storage.get_pdf_dir()
            os.makedirs(pdf_dir, exist_ok=True)
            with zipfile.ZipFile(file) as zf:
                for member in zf.namelist():
                    if member.startswith("pdfs/"):
                        target = os.path.join(pdf_dir, os.path.basename(member))
                        with zf.open(member) as src, open(target, "wb") as dst:
                            shutil.copyfileobj(src, dst)
                    elif not member.endswith("/"):
                        target = os.path.join(data_path, os.path.basename(member))
                        with zf.open(member) as src, open(target, "wb") as dst:
                            shutil.copyfileobj(src, dst)
            flash("Backup restored. Your data was replaced from the ZIP.", "success")
            from account import telemetry

            telemetry.send_event("backup_import")
            return redirect(url_for("backup_import"))
        return render_template("backup_import.html", error=None)
