"""Copy every LTI 1.3 passport into the reusable configuration catalog.

Data-only: the schema arrives in ``0024``. Every old passport is copied with its
nine historical fields, a matching destination row is reused without refreshing
its other metadata, and every placement whose old foreign key is set is linked to
its copy. A conflict aborts the whole transaction instead of merging or skipping.
Reads, inserts and lookups are bounded by ``BATCH_SIZE``, so no table is ever held
in memory at once and legacy primary keys below zero are covered as well.
"""
from django.db import migrations

BATCH_SIZE = 500

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


def _copy_passports(Passport, Reusable, alias, counts):
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
            for copy in new.filter(passport_id__in=list(source_by_uuid)).values('pk', *COPIED_FIELDS)
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
            # pre-population can make these legacy fields diverge.
            differing = [field for field in COPIED_FIELDS if copy[field] != getattr(passport, field)]
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
        # falling back to model defaults.
        new.bulk_create(
            [Reusable(**{field: getattr(passport, field) for field in COPIED_FIELDS}) for passport in missing],
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
    """Copy every passport and link every placement bound to one."""
    alias = schema_editor.connection.alias
    Passport = apps.get_model('lti_consumer', 'Lti1p3Passport')
    Reusable = apps.get_model('lti_consumer', 'ReusableLtiConfiguration')
    Placement = apps.get_model('lti_consumer', 'LtiConfiguration')

    counts = {'read': 0, 'inserted': 0, 'reused': 0, 'linked': 0, 'null_old_fk': 0}
    _copy_passports(Passport, Reusable, alias, counts)
    _link_placements(Placement, Passport, Reusable, alias, counts)
    print(f"0025_copy_lti1p3_passports: {_counts_message(counts, aborts=0)}")


class Migration(migrations.Migration):
    """Copy passport data and link placements; no schema changes."""

    dependencies = [
        ('lti_consumer', '0024_create_reusable_lti_configuration'),
    ]

    operations = [
        migrations.RunPython(copy_passports, migrations.RunPython.noop),
    ]
