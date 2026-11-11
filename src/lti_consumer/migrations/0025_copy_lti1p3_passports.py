"""Copy every LTI 1.3 passport into the reusable configuration catalog.

Data-only: the schema arrives in ``0024``. Every old passport is copied with its
nine historical fields, a matching destination row is reused without refreshing
its other metadata, and every placement whose old foreign key is set is linked to
its copy. A conflict aborts the whole transaction instead of merging or skipping.

New copies also get a ``version`` and a single creation context inferred from the
placements bound to the old foreign key (decision 0005). ``CONFIG_EXTERNAL``
placements are excluded from inference but still linked. Only the old foreign key
binds a placement to a passport, so a placement with a conflicting destination
binding is still eligible and aborts later while linking.

Reads, inserts and lookups are bounded by ``BATCH_SIZE``, so no table is ever held
in memory at once and legacy primary keys below zero are covered as well. Only the
historical models and this migration's database alias are used: no modulestore,
organization registry, provider, key or client ID generation.
"""
from ccx_keys.locator import CCXLocator
from django.db import migrations
from opaque_keys.edx.locator import CourseLocator

BATCH_SIZE = 500

# The values stored by the historical placement and catalog models. Migrations must not
# import runtime models, so the few constants this one needs are repeated here.
LTI_1P1 = 'lti_1p1'
LTI_1P3 = 'lti_1p3'
COURSE = 'course'
ORGANIZATION = 'organization'
SITE = 'site'
CONFIG_EXTERNAL = 'CONFIG_EXTERNAL'

# The only values a passport carries; the new row allocates its own id and timestamps.
COPIED_FIELDS = (
    'passport_id',
    'name',
    'context_key',
    'lti_1p3_internal_private_key',
    'lti_1p3_internal_private_key_id',
    'lti_1p3_internal_public_jwk',
    'lti_1p3_client_id',
    'lti_1p3_tool_public_key',
    'lti_1p3_tool_keyset_url',
)

# ``context_key`` is inferred for new copies, so replay compares only values that are
# preserved verbatim: comparing the raw key would reject every copy with a canonical key.
REPLAY_FIELDS = tuple(field for field in COPIED_FIELDS if field != 'context_key')


def _batches(queryset):
    """Yield primary-key ordered batches, negative legacy keys included, with bounded memory."""
    last_pk = None
    while True:
        page = queryset if last_pk is None else queryset.filter(pk__gt=last_pk)
        # The slice is a SQL LIMIT: list() evaluates only BATCH_SIZE rows, not the whole table.
        batch = list(page.order_by('pk')[:BATCH_SIZE])
        if not batch:
            return
        yield batch
        last_pk = batch[-1].pk


def _counts_message(counts, aborts):
    """Render safe counters only: no key, secret or other stored value appears here."""
    return (
        f"read={counts['read']} inserted={counts['inserted']} reused={counts['reused']} "
        f"linked={counts['linked']} null_old_fk={counts['null_old_fk']} aborts={aborts}"
    )


def _divergence_message(conflicts, counts):
    """Describe divergent copies by identifier and field name only."""
    details = '; '.join(
        f"passport {passport_id} differs in {', '.join(fields)}" for passport_id, fields in conflicts
    )
    return (
        f"0025_copy_lti1p3_passports: destination copies diverge ({details}); "
        f"aborting with {_counts_message(counts, aborts=1)}"
    )


def _course(location):
    """Return ``(canonical course key, normalized organization)`` for a supported course.

    A missing location, a library and a CCX course are unsupported and return ``None``,
    which forces the whole configuration to ``site``. Parsing a stored location is a pure
    key operation: no block is loaded.
    """
    # ``context_key`` is the block's course context (or its library), already parsed by the
    # historical UsageKeyField. ``course_key`` is deprecated on newer library keys.
    course_key = getattr(location, 'context_key', None)
    if not isinstance(course_key, CourseLocator) or isinstance(course_key, CCXLocator):
        return None
    if not all((course_key.org, course_key.course, course_key.run)):
        return None
    # The same canonical form the service layer stores: no branch and no version.
    course_key = course_key.for_branch(None).version_agnostic()
    canonical, organization = str(course_key), course_key.org.strip().lower()
    if not canonical or not organization:
        # Course and organization contexts require a non-blank key, site is the only safe fit.
        return None
    return canonical, organization


def _state():
    """One passport's fixed-size inference accumulator; no per-placement value is retained."""
    return {
        'version': None,
        'uniform_version': True,
        'course': None,
        'multiple_courses': False,
        'organization': None,
        'uniform_organization': True,
        'unsupported': False,
    }


def _collect(state, version, location):
    """Fold one eligible placement into its passport's fixed-size state."""
    if version not in (LTI_1P1, LTI_1P3):
        state['uniform_version'] = False
    elif state['version'] is None:
        state['version'] = version
    elif version != state['version']:
        state['uniform_version'] = False
    course = _course(location)
    if course is None:
        state['unsupported'] = True
        return
    canonical, organization = course
    if state['course'] is None:
        state['course'] = canonical
        state['organization'] = organization
    elif canonical != state['course']:
        state['multiple_courses'] = True
        if organization != state['organization']:
            state['uniform_organization'] = False


def _inferred(state):
    """Resolve one passport's inferred ``version``, ``context_type`` and ``context_key``."""
    version = state['version'] if state['uniform_version'] else None
    if version not in (LTI_1P1, LTI_1P3):
        version = None
    if state['unsupported'] or state['course'] is None:
        context_type, context_key = SITE, ''
    elif not state['multiple_courses']:
        context_type, context_key = COURSE, state['course']
    elif state['uniform_organization']:
        context_type, context_key = ORGANIZATION, state['organization']
    else:
        context_type, context_key = SITE, ''
    return {'version': version, 'context_type': context_type, 'context_key': context_key}


def _infer(Placement, alias, passports):
    """Infer every new copy's catalog metadata from its eligible placements.

    Eligibility is the old foreign key alone, excluding ``CONFIG_EXTERNAL``; the new
    binding is deliberately not part of the predicate. Placements are read in
    primary-key pages, and each passport keeps only a fixed-size accumulator, so neither
    a large table nor a passport with many distinct rows grows memory without bound.
    """
    states = {passport.pk: _state() for passport in passports}
    eligible = Placement.objects.using(alias).filter(
        lti_1p3_passport_id__in=list(states),
    ).exclude(config_store=CONFIG_EXTERNAL)
    for batch in _batches(eligible):
        for placement in batch:
            _collect(states[placement.lti_1p3_passport_id], placement.version, placement.location)
    return {pk: _inferred(state) for pk, state in states.items()}


def _copy_passports(Passport, Reusable, Placement, alias, counts):
    """Copy every passport, reusing a matching copy as-is, and update the shared counters."""
    old = Passport.objects.using(alias)
    new = Reusable.objects.using(alias)

    for batch in _batches(old):
        counts['read'] += len(batch)
        # Look up existing destinations once per batch by the preserved passport UUID; the
        # primary keys are allocated independently, so only that value can match a copy.
        source_by_uuid = {passport.passport_id: passport for passport in batch}
        copies = {
            copy['passport_id']: copy
            for copy in new.filter(passport_id__in=list(source_by_uuid)).values('pk', *REPLAY_FIELDS)
        }
        # Three outcomes per passport: absent (queued for insert), an exact copy (reused
        # without touching its authored metadata), or a divergent copy (collected to abort).
        missing = []
        conflicts = []
        for passport_id, passport in source_by_uuid.items():
            copy = copies.get(passport_id)
            if copy is None:
                missing.append(passport)
                continue
            # Handles edge case where a noop reverse preserves copies; edits before replay or manual
            # pre-population can make these legacy fields diverge. Inferred metadata is not compared.
            differing = [field for field in REPLAY_FIELDS if copy[field] != getattr(passport, field)]
            if differing:
                conflicts.append((passport_id, differing))
                continue
            counts['reused'] += 1
        if conflicts:
            # Deliberately abort: rolling back every earlier batch beats overwriting authored data.
            raise RuntimeError(_divergence_message(conflicts, counts))
        if not missing:
            continue
        # All nine source fields are passed explicitly so blanks and identity survive instead of
        # falling back to model defaults. Only new rows get inferred catalog metadata.
        inference = _infer(Placement, alias, missing)
        new.bulk_create(
            [
                Reusable(**{
                    **{field: getattr(passport, field) for field in COPIED_FIELDS},
                    **inference[passport.pk],
                })
                for passport in missing
            ],
            batch_size=BATCH_SIZE,
        )
        counts['inserted'] += len(missing)


def _destination_ids(Passport, Reusable, alias, passport_pks):
    """Resolve one batch of old passport primary keys to their copied configuration primary keys."""
    passport_id_by_pk = dict(
        Passport.objects.using(alias).filter(pk__in=passport_pks).values_list('pk', 'passport_id')
    )
    pk_by_passport_id = dict(
        Reusable.objects.using(alias)
        .filter(passport_id__in=list(passport_id_by_pk.values()))
        .values_list('passport_id', 'pk')
    )
    return {
        passport_pk: pk_by_passport_id[passport_id]
        for passport_pk, passport_id in passport_id_by_pk.items()
        if passport_id in pk_by_passport_id
    }


def _link_placements(Placement, Passport, Reusable, alias, counts):
    """Link placements to their copies, leaving placements without an old passport alone."""
    placements = Placement.objects.using(alias)

    for batch in _batches(placements):
        referenced = {
            placement.lti_1p3_passport_id for placement in batch if placement.lti_1p3_passport_id is not None
        }
        destinations = _destination_ids(Passport, Reusable, alias, referenced) if referenced else {}
        pending = {}
        for placement in batch:
            if placement.lti_1p3_passport_id is None:
                counts['null_old_fk'] += 1
                continue
            destination_pk = destinations.get(placement.lti_1p3_passport_id)
            if destination_pk is None:
                raise RuntimeError(
                    f"0025_copy_lti1p3_passports: placement {placement.pk} references passport "
                    f"{placement.lti_1p3_passport_id}, which has no copied configuration; "
                    f"aborting with {_counts_message(counts, aborts=1)}"
                )
            if placement.reusable_configuration_id is None:
                pending.setdefault(destination_pk, []).append(placement.pk)
            elif placement.reusable_configuration_id != destination_pk:
                raise RuntimeError(
                    f"0025_copy_lti1p3_passports: placement {placement.pk} is bound to reusable "
                    f"configuration {placement.reusable_configuration_id}, expected {destination_pk} "
                    f"for passport {placement.lti_1p3_passport_id}; "
                    f"aborting with {_counts_message(counts, aborts=1)}"
                )
        for destination_pk, placement_pks in pending.items():
            counts['linked'] += placements.filter(
                pk__in=placement_pks, reusable_configuration__isnull=True
            ).update(reusable_configuration_id=destination_pk)


def copy_passports(apps, schema_editor):
    """Copy every passport, infer new catalog metadata and link every placement bound to one."""
    alias = schema_editor.connection.alias
    Passport = apps.get_model('lti_consumer', 'Lti1p3Passport')
    Reusable = apps.get_model('lti_consumer', 'ReusableLtiConfiguration')
    Placement = apps.get_model('lti_consumer', 'LtiConfiguration')

    counts = {'read': 0, 'inserted': 0, 'reused': 0, 'linked': 0, 'null_old_fk': 0}
    _copy_passports(Passport, Reusable, Placement, alias, counts)
    _link_placements(Placement, Passport, Reusable, alias, counts)
    print(f"0025_copy_lti1p3_passports: {_counts_message(counts, aborts=0)}")


class Migration(migrations.Migration):
    """Copy passport data, infer new catalog metadata and link placements; no schema changes."""

    dependencies = [
        ('lti_consumer', '0024_create_reusable_lti_configuration'),
    ]

    operations = [
        migrations.RunPython(copy_passports, migrations.RunPython.noop),
    ]
