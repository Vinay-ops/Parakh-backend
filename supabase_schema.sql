-- Run this once in Supabase Dashboard -> SQL Editor.
-- Supabase Auth owns auth.users; this script creates only application tables.

create table if not exists public.profiles (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null unique references auth.users(id) on delete cascade,
  full_name text,
  email text,
  profile_image_url text,
  role text,
  department text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.inspections (
  id uuid primary key default gen_random_uuid(),
  inspection_id varchar(32) not null unique,
  user_id uuid not null references auth.users(id) on delete cascade,
  product_name varchar(255),
  product_category varchar(100),
  product_image_url text,
  inspection_date date,
  inspection_time time,
  compliance_status varchar(32) default 'PENDING_ML',
  compliance_score double precision,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.extracted_information (
  id uuid primary key default gen_random_uuid(),
  inspection_id uuid not null unique references public.inspections(id) on delete cascade,
  common_product_name varchar(255), manufacturer_name varchar(255), manufacturer_address text,
  packer_name varchar(255), packer_address text, importer_name varchar(255), importer_address text,
  multi_product_names jsonb, multi_product_quantities jsonb,
  net_quantity_value double precision, net_quantity_unit varchar(50), number_count integer,
  mrp double precision, mrp_tax_wording varchar(255), manufacture_or_import_date varchar(255),
  consumer_care_name varchar(255), consumer_care_address text, consumer_care_phone varchar(50),
  consumer_care_email varchar(255), commodity_dimensions varchar(255),
  created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);

create table if not exists public.compliance_results (
  id uuid primary key default gen_random_uuid(),
  inspection_id uuid not null references public.inspections(id) on delete cascade,
  rule_name varchar(255) not null, status varchar(32) not null, reason text,
  required_value varchar(255), detected_value varchar(255), bounding_box jsonb,
  created_at timestamptz not null default now()
);

create table if not exists public.complaints (
  id uuid primary key default gen_random_uuid(),
  complaint_id varchar(32) not null unique,
  inspection_id uuid references public.inspections(id) on delete set null,
  user_id uuid not null references auth.users(id) on delete cascade,
  product_name varchar(255), complaint_title varchar(255) not null, description text,
  category varchar(100), priority varchar(20) default 'MEDIUM', status varchar(20) default 'OPEN',
  created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);

alter table public.profiles enable row level security;
alter table public.inspections enable row level security;
alter table public.extracted_information enable row level security;
alter table public.compliance_results enable row level security;
alter table public.complaints enable row level security;

drop policy if exists profiles_owner on public.profiles;
create policy profiles_owner on public.profiles for all using (auth.uid()::text = user_id::text) with check (auth.uid()::text = user_id::text);
drop policy if exists inspections_owner on public.inspections;
create policy inspections_owner on public.inspections for all using (auth.uid()::text = user_id::text) with check (auth.uid()::text = user_id::text);
drop policy if exists extracted_owner on public.extracted_information;
create policy extracted_owner on public.extracted_information for all using (
  exists (select 1 from public.inspections i where i.id::text = inspection_id::text and i.user_id::text = auth.uid()::text)
) with check (
  exists (select 1 from public.inspections i where i.id::text = inspection_id::text and i.user_id::text = auth.uid()::text)
);
drop policy if exists compliance_owner on public.compliance_results;
create policy compliance_owner on public.compliance_results for all using (
  exists (select 1 from public.inspections i where i.id::text = inspection_id::text and i.user_id::text = auth.uid()::text)
) with check (
  exists (select 1 from public.inspections i where i.id::text = inspection_id::text and i.user_id::text = auth.uid()::text)
);
drop policy if exists complaints_owner on public.complaints;
create policy complaints_owner on public.complaints for all using (auth.uid()::text = user_id::text) with check (auth.uid()::text = user_id::text);

insert into storage.buckets (id, name, public)
values ('product-images', 'product-images', true)
on conflict (id) do nothing;

drop policy if exists product_images_upload on storage.objects;
create policy product_images_upload on storage.objects for insert to authenticated
with check (bucket_id = 'product-images' and (storage.foldername(name))[1] = (select auth.uid()::text));
drop policy if exists product_images_read on storage.objects;
create policy product_images_read on storage.objects for select to public
using (bucket_id = 'product-images');
