from django.db import models


class StorageLocation(models.Model):
    name = models.CharField(max_length=32)

    def __str__(self):
        return self.name


class DataType(models.Model):
    name = models.CharField(max_length=64)

    def __str__(self):
        return self.name


class ShareType(models.Model):
    name = models.CharField(max_length=64)

    def __str__(self):
        return self.name


class DMP(models.Model):
    dmp_id = models.IntegerField()
    type = models.IntegerField()
    template_name = models.CharField(max_length=128, blank=True, null=True)
    human_participants = models.BooleanField(blank=True, null=True)
    personal_data = models.BooleanField(blank=True, null=True)
    confidential_data = models.BooleanField(blank=True, null=True)

    storage_locations = models.ManyToManyField(
        to=StorageLocation, blank=True, related_name="dmps"
    )
    data_amount = models.IntegerField(blank=True, null=True)
    data_amount_public = models.IntegerField(blank=True, null=True)
    data_types_public = models.ManyToManyField(
        to=DataType, blank=True, related_name="dmps"
    )
    share_types = models.ManyToManyField(to=ShareType, blank=True, related_name="dmps")

    def __str__(self):
        return str(self.dmp_id)

    def save(self, *args, **kwargs):
        # TODO: Update DMP via department/users PATCH
        super().save(*args, **kwargs)


class FacultyDepartment(models.Model):
    name = models.CharField(max_length=16)

    def __str__(self):
        return self.name


class Position(models.Model):
    name = models.CharField(max_length=16)

    def __str__(self):
        return self.name


class DataUser(models.Model):
    dmp = models.ForeignKey(to=DMP, related_name="users", on_delete=models.CASCADE)
    email_hash = models.CharField(max_length=32)
    faculty_department = models.ForeignKey(
        to=FacultyDepartment,
        blank=True,
        null=True,
        related_name="users",
        on_delete=models.CASCADE,
    )

    position = models.ForeignKey(
        to=Position,
        null=True,
        blank=True,
        related_name="users",
        on_delete=models.CASCADE,
    )

    def __str__(self):
        return "DMP: " + str(self.dmp) + " Email hash: " + self.email_hash
