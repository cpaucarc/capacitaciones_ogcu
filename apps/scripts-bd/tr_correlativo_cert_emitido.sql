CREATE OR REPLACE FUNCTION public.genera_correlativo_cert()
 RETURNS trigger
 LANGUAGE plpgsql
AS $function$
BEGIN
  NEW.correlativo := (SELECT LPAD(nextval('correlativo_cert_secuencia') :: TEXT, 5, '0') || '-' || date_part('year', now()));
  RETURN NEW;
END;$function$;

CREATE TRIGGER trg_correlativo_cert
    BEFORE INSERT
    ON public.capacitacion_certemitido
    FOR EACH ROW
    EXECUTE PROCEDURE public.genera_correlativo_cert();
