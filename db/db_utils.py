def duplicate_row(row, exclude_fields=["id", "created_at", "updated_at"]):
    cls = type(row)
    data = {
        column.name: getattr(row, column.name)
        for column in cls.__table__.columns
        if column.name not in exclude_fields
    }
    return cls(**data)
