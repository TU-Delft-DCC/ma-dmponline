from django.contrib import admin
from stats.models import (
    DMP,
    DataType,
    FacultyDepartment,
    Position,
    ShareType,
    StorageLocation,
    DataUser,
)


class DataUserInline(admin.TabularInline):
    model = DataUser


class DMPAdmin(admin.ModelAdmin):
    inlines = [DataUserInline]


admin.site.register(DMP, DMPAdmin)
admin.site.register(DataType)
admin.site.register(FacultyDepartment)
admin.site.register(Position)
admin.site.register(ShareType)
admin.site.register(StorageLocation)
admin.site.register(DataUser)
