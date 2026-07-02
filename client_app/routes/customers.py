"""Customer CRUD routes."""

from urllib.parse import unquote

from flask import redirect, render_template, request, url_for

import storage
from invoicing.address import normalize_au_address
from invoicing.validators import normalize_abn


def register_customer_routes(app):
    @app.route("/customers")
    def customers_list():
        customers = storage.load_customers()
        return render_template("customers.html", customers=customers)

    @app.route("/customers/add", methods=["GET", "POST"])
    def customers_add():
        if request.method == "POST":
            name = request.form.get("name", "").strip()
            address_line1 = request.form.get("address_line1", "").strip()
            address_line2 = request.form.get("address_line2", "").strip()
            suburb = request.form.get("suburb", "").strip()
            state = request.form.get("state", "").strip()
            postcode = request.form.get("postcode", "").strip()
            abn = request.form.get("abn", "").strip()
            email = request.form.get("email", "").strip()

            if not name:
                return render_template(
                    "edit_customer.html",
                    customer=None,
                    form={
                        "name": name,
                        "address_line1": address_line1,
                        "address_line2": address_line2,
                        "suburb": suburb,
                        "state": state,
                        "postcode": postcode,
                        "abn": abn,
                        "email": email,
                    },
                    error="Enter a customer name.",
                    is_add=True,
                )

            if storage.customer_name_exists(name):
                return render_template(
                    "edit_customer.html",
                    customer=None,
                    form={
                        "name": name,
                        "address_line1": address_line1,
                        "address_line2": address_line2,
                        "suburb": suburb,
                        "state": state,
                        "postcode": postcode,
                        "abn": abn,
                        "email": email,
                    },
                    error="A customer with this name already exists.",
                    is_add=True,
                )

            try:
                addr = normalize_au_address(
                    line1=address_line1,
                    line2=address_line2,
                    suburb=suburb,
                    state=state,
                    postcode=postcode,
                )
                abn = normalize_abn(abn)
            except ValueError as exc:
                return render_template(
                    "edit_customer.html",
                    customer=None,
                    form={
                        "name": name,
                        "address_line1": address_line1,
                        "address_line2": address_line2,
                        "suburb": suburb,
                        "state": state,
                        "postcode": postcode,
                        "abn": abn,
                        "email": email,
                    },
                    error=str(exc),
                    is_add=True,
                )

            customers = storage.load_customers()
            customers[name] = {**addr, "abn": abn, "email": email}
            storage.save_customers(customers)
            from account import telemetry

            telemetry.send_event("first_customer")
            return redirect(url_for("customers_list"))

        return render_template(
            "edit_customer.html",
            customer=None,
            form={
                "name": "",
                "address_line1": "",
                "address_line2": "",
                "suburb": "",
                "state": "",
                "postcode": "",
                "abn": "",
                "email": "",
            },
            error=None,
            is_add=True,
        )

    @app.route("/customers/edit/<name>", methods=["GET", "POST"])
    def customers_edit(name):
        name = unquote(name)
        customers = storage.load_customers()

        if name not in customers:
            return redirect(url_for("customers_list"))

        customer = customers[name]

        if request.method == "POST":
            address_line1 = request.form.get("address_line1", "").strip()
            address_line2 = request.form.get("address_line2", "").strip()
            suburb = request.form.get("suburb", "").strip()
            state = request.form.get("state", "").strip()
            postcode = request.form.get("postcode", "").strip()
            abn = request.form.get("abn", "").strip()
            email = request.form.get("email", "").strip()
            try:
                addr = normalize_au_address(
                    line1=address_line1,
                    line2=address_line2,
                    suburb=suburb,
                    state=state,
                    postcode=postcode,
                )
                abn = normalize_abn(abn)
            except ValueError as exc:
                return render_template(
                    "edit_customer.html",
                    customer=name,
                    form={
                        "name": name,
                        "address_line1": address_line1,
                        "address_line2": address_line2,
                        "suburb": suburb,
                        "state": state,
                        "postcode": postcode,
                        "abn": abn,
                        "email": email,
                    },
                    error=str(exc),
                    is_add=False,
                )
            customers[name] = {**addr, "abn": abn, "email": email}
            storage.save_customers(customers)
            return redirect(url_for("customers_list"))

        return render_template(
            "edit_customer.html",
            customer=name,
            form={
                "name": name,
                "address_line1": customer.get("address_line1", ""),
                "address_line2": customer.get("address_line2", ""),
                "suburb": customer.get("suburb", ""),
                "state": customer.get("state", ""),
                "postcode": customer.get("postcode", ""),
                "abn": customer.get("abn", ""),
                "email": customer.get("email", ""),
            },
            error=None,
            is_add=False,
        )

    @app.route("/customers/delete/<name>", methods=["POST"])
    def customers_delete(name):
        name = unquote(name)
        customers = storage.load_customers()
        if name in customers:
            del customers[name]
            storage.save_customers(customers)
        return redirect(url_for("customers_list"))
