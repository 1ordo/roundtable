import { useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { fetchMe } from '../api/client'

export function useMe() {
  const query = useQuery({
    queryKey: ['me'],
    queryFn: fetchMe,
    retry: false,
    staleTime: 5 * 60_000,
    // A tab left open all evening should notice a dead session when it is
    // brought back to the front, not on the next click that fails.
    refetchOnWindowFocus: true,
  })

  /* Preferences that the browser has to know about live on the root
     element, so CSS and the animation helpers can read them without
     threading state through every component. */
  const reduceMotion = query.data?.user?.prefs?.reduce_motion
  useEffect(() => {
    if (reduceMotion) document.documentElement.dataset.reduceMotion = 'true'
    else delete document.documentElement.dataset.reduceMotion
  }, [reduceMotion])

  return query
}
