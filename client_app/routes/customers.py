"""Customer CRUD routes."""

from urllib.parse import unquote

from flask import redirect, render_template, request, url_for

import storage


def register_customer_routes(app):
    @app.route("/customers")
    def customers_list():
        customers = storage.load_customers()
        return render_template("customers.html", customers=customers)

    @app.route("/customers/add", methods=["GET", "POST"])
    def customers_add():
        if request.method == "POST":
            name = request.form.get("name", "").strip()
            address = request.form.get("address", "").strip()
            abn = request.form.get("abn", "").strip()
            email = request.form.get("email", "").strip()

            if not name:
                return render_template(
                    "edit_customer.html",
                    customer=None,
                    form={"name": name, "address": address, "abn": abn, "email": email},
                    error="Enter a customer name.",
                    is_add=True,
                )

            if storage.customer_name_exists(name):
                return render_template(
                    "edit_customer.html",
                    customer=None,
                    form={"name": name, "address": address, "abn": abn, "email": email},
                    error="A customer with this name already exists.",
                    is_add=True,
                )

            customers = storage.load_customers()
            customers[name] = {"address": address, "abn": abn, "email": email}
            storage.save_customers(customers)
            from account import telemetry

            telemetry.send_event("first_customer")
            return redirect(url_for("customers_list"))

        return render_template(
            "edit_customer.html",
            customer=None,
            form={"name": "", "address": "", "abn": "", "email": ""},
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
            address = request.form.get("address", "").strip()
            abn = request.form.get("abn", "").strip()
            email = request.form.get("email", "").strip()
            customers[name] = {"address": address, "abn": abn, "email": email}
            storage.save_customers(customers)
            return redirect(url_for("customers_list"))

        return render_template(
            "edit_customer.html",
            customer=name,
            form={
                "name": name,
                "address": customer.get("address", ""),
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
