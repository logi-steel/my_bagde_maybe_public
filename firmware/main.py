# Badge entry point. The real work lives in the `badge` package.
try:
    import badge.app as app
    app.run()
except Exception as e:  # noqa - never leave the badge dead without a way back
    import recover
    recover.handle(e)
