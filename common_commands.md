SELECT *
FROM public.events
WHERE title ILIKE '%Gaza%' OR title ILIKE '%gaza%' 
ORDER BY volume DESC;

SELECT *
FROM public.events
WHERE title ILIKE '%Gaza%' OR title ILIKE '%gaza%' 
ORDER BY volume DESC;

TRUNCATE TABLE public.events;