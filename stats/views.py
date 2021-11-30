import json
from django.db.models import Count, Q
from django.http import JsonResponse, HttpResponse
from django.template.response import TemplateResponse
from stats.models import DMP

AGGREGATES = [
    ("template_name", "Template kind"),
    ("users__faculty_department__name", "Faculty-Department"),
    ("human_participants", "Work with human participants"),
    ("personal_data", "Work with personal data"),
    ("confidential_data", "Work with confidential data"),
    ("storage_locations__name", "Used storage location"),
    ("data_amount", "Data amount"),
    ("data_types_public__name", "What types of data will be shared"),
    ("share_types__name", "How will research data be shared"),
    ("data_amount_public", "How much data will be made public"),
]


def index(request):
    types = [
        [
            [question[1], "total"],
            *list(
                DMP.objects.filter(**{})
                .values(question[0])
                .annotate(total=Count("*"))  # Count("*") includes null values
                .values_list(question[0], "total")
            ),
        ]
        for question in AGGREGATES
    ]
    # replace null (None) with "Unknown" (for Google Chart to understand it)
    types = replace_whr(types)

    return JsonResponse({"types": types}, safe=False)


def stats(request):
    questions = [
        {
            question: list(
                DMP.objects.all()
                .order_by(question[0])
                .values_list(question[0], flat=True)
                .distinct()
            )
        }
        for question in AGGREGATES
    ]
    return TemplateResponse(request, "stats.html", {"questions": questions})


def stats_filter(request):
    qss = Q()
    for item in request.GET:
        qs = Q()
        for search in request.GET.getlist(item):
            if search != "None":
                qs |= Q(**{item[:-2] + "__in": [search]})
            else:
                qs |= Q(**{item[:-2] + "__isnull": True})
        qss &= qs

    types = [
        [
            [question[1], "total"],
            *list(
                DMP.objects.filter(qss)
                .values(question[0])
                .distinct()
                .order_by(question[0])
                .annotate(total=Count("*"))  # Count("*") includes null values
                .values_list(question[0], "total")
            ),
        ]
        for question in AGGREGATES
    ]

    # replace null (None) with "Unknown" (for Google Chart to understand it)
    types = replace_whr(types)

    return TemplateResponse(
        request, "stats_filter.html", {"filtered_data": json.dumps(types)}
    )


def replace_whr(types):
    for i in range(len(types)):
        for j in range(1, len(types[i])):
            if types[i][j][0] is None:
                types[i][j] = "Unknown", types[i][j][1]
            if types[i][j][0] is False:
                types[i][j] = "No", types[i][j][1]
            if types[i][j][0] is True:
                types[i][j] = "Yes", types[i][j][1]
            if type(types[i][j][0]) is int:
                types[i][j] = str(types[i][j][0]), types[i][j][1]
    return types
