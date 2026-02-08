import * as React from 'react';

const VisuallyHiddenRoot = React.forwardRef<HTMLSpanElement, React.HTMLAttributes<HTMLSpanElement>>(
    ({ style, ...props }, ref) => {
        return (
            <span
                ref={ref}
                style={{
                    border: 0,
                    clip: 'rect(0 0 0 0)',
                    height: '1px',
                    margin: '-1px',
                    overflow: 'hidden',
                    padding: 0,
                    position: 'absolute',
                    width: '1px',
                    whiteSpace: 'nowrap',
                    wordWrap: 'normal',
                    ...style,
                }}
                {...props}
            />
        );
    }
);
VisuallyHiddenRoot.displayName = 'VisuallyHidden';

export const Root = VisuallyHiddenRoot;
