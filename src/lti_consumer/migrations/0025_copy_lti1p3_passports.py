"""Copy passports into the reusable catalog (data-only; schema is ``0024``).

for each old passport, orphans included, in primary-key order (negative keys too)
  find destination by passport_id
  absent: copy legacy identity, credentials and keys; infer from
    old-FK placements excluding CONFIG_EXTERNAL:
      version: unanimous lti_1p1 or lti_1p3, otherwise NULL
      context:
        missing location, no eligible placement, or any unsupported -> site, empty
        one canonical course -> course, canonical context_key
        several courses in one normalized organization -> organization, trimmed lowercase org
        otherwise -> site, empty
    inference applies to new copies only; the old raw context_key is kept
  existing: compare preserved fields only, never context_key/version/context_type
    match -> reuse unchanged, authored metadata is not refreshed
    differ -> abort the whole transaction

then link every placement with an old FK set, CONFIG_EXTERNAL included
  null old FK -> unchanged
  conflicting existing destination binding -> abort the whole transaction
  destination binding never filters inference eligibility

Constraints:
  data-only, no schema change here; historical models and this alias only
  reads, inserts and lookups use BATCH_SIZE pages, fixed memory
  no modulestore, registry, provider, key or client-ID generation
"""
from ccx_keys.locator import CCXLocator
from django.db import migrations
from opaque_keys.edx.locator import CourseLocator

BATCH_SIZE = 500

# Keep migration values here instead of importing current models.
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

# The inferred ``context_key`` may differ from the old raw key, so replay skips it.
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
    """Name the copies that differ and the fields, never their values."""
    details = '; '.join(
        f"passport {passport_id} differs in {', '.join(fields)}" for passport_id, fields in conflicts
    )
    return (
        f"0025_copy_lti1p3_passports: destination copies diverge ({details}); "
        f"aborting with {_counts_message(counts, aborts=1)}"
    )


def _course(location):
    """Return ``(canonical course key, organization)`` for a supported course, else ``None``.

    Missing location, library and CCX are unsupported, which forces the whole
    configuration to ``site``. Read only the stored key; do not load the XBlock.
    """
    # The stored location is already parsed; use its course context (a library has its own).
    course_key = getattr(location, 'context_key', None)
    if not isinstance(course_key, CourseLocator) or isinstance(course_key, CCXLocator):
        return None
    if not all((course_key.org, course_key.course, course_key.run)):
        return None
    # The same canonical form the service layer stores: no branch and no version.
    course_key = course_key.for_branch(None).version_agnostic()
    canonical, organization = str(course_key), course_key.org.strip().lower()
    if not canonical or not organization:
        # A blank key cannot be a course or organization context, so treat it as unsupported.
        return None
    return canonical, organization


def _state():
    """Keep one version, course and organization per passport, plus flags."""
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
    """Update the passport summary from one eligible placement."""
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
    """Choose version, context type and key from the saved summary."""
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
    """Infer catalog metadata for new copies from their old-FK placements.

    new copies only
      eligible: the old FK points to one of these passports, config_store is not CONFIG_EXTERNAL
      an existing conflicting destination binding does not change eligibility
      placements are read in primary-key pages, so memory stays flat
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
    """Copy each passport, reuse a matching copy as-is, and update the shared counters."""
    old = Passport.objects.using(alias)
    new = Reusable.objects.using(alias)

    for batch in _batches(old):
        counts['read'] += len(batch)
        # Match copies by passport_id: each table allocates its own primary keys.
        source_by_uuid = {passport.passport_id: passport for passport in batch}
        copies = {
            copy['passport_id']: copy
            for copy in new.filter(passport_id__in=list(source_by_uuid)).values('pk', *REPLAY_FIELDS)
        }
        # Three outcomes per passport: absent (queued for insert), an exact copy (reused
        # without touching its other metadata), or a copy that differs (collected to abort).
        missing = []
        conflicts = []
        for passport_id, passport in source_by_uuid.items():
            copy = copies.get(passport_id)
            if copy is None:
                missing.append(passport)
                continue
            # A copy may already exist (noop reverse, manual row or edits): compare the kept
            # fields and reuse it, or abort below if they differ. Inferred fields are not compared.
            differing = [field for field in REPLAY_FIELDS if copy[field] != getattr(passport, field)]
            if differing:
                conflicts.append((passport_id, differing))
                continue
            counts['reused'] += 1
        if conflicts:
            # Deliberately abort: undoing earlier batches is safer than overwriting a copy's fields.
            raise RuntimeError(_divergence_message(conflicts, counts))
        if not missing:
            continue
        # Pass every copied field explicitly so blanks and identity are kept, not model defaults.
        # New rows then get inferred metadata in place of the old raw context key.
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
