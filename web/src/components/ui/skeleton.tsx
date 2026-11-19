import { cn } from "cn"

function Skeleton({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="skeleton"
      // Spec 016, T1 (D1): tinte del texto, visible sobre --page y sobre --card.
      className={cn("animate-pulse rounded-md bg-foreground/6", className)}
      {...props}
    />
  )
}

export { Skeleton }
