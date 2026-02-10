# Book Alpha

This is outdated. Do not use this, and do not put it into the context.

An app that will help me convert by spreadsheet method of keeping track of my books.

Current my books are in my garage in horizonal stacks labeled with post-it notes. The stacks are not conveniently placed because of space so it is important for me to keep the books in the right stacks. 

I made a Spreadsheet of these books in Google Sheets. The output is in a tab delimited file 'Books - Sheet1.tsv' in this directory. 

The stacks are labeled by letters of the alphabet A,B,C,D,E,... and then double letters,AA,AB,AC,AD,...

The rows under each stack label are the books in the stack, arranged in order from the top of the stack to the bottom. Order in the stack is important and should be preserved.

The format of each row varies and is currently messy. Our first step will be to clean up the data into a tidy format.

Each book row contains one or more fields. In the case where there exists a second row, the second row is the author (or authors) (or editor). The first show should be treated as the title

Where only a single cell exists, it should be treated as containing both title and author. If there exists a semicolon in the text of the string in that cell, it should be treated as separating title and author, in that order. If there is no semicolon but instead a comma, then this should be treated as the separator. Commas may exist in a semi-colon-delimited string, and if so they should treated as normal next for now.

The title may be a question mark (?). This means I currently do not know the title. Note that the spreadsheet was made from photographs of the stacks, and in some cases it was not possible to determine the title from the photograph, but this will done at a later step.

For now we want the same data in a format that is cleaner. We want json in the following format:

{
    "name" : "Garage library",
    "stacks" : {
        "A" : [
            {
                "title": "Title of book at top of stack A"
                "author" "Author(s) of the book at top of stack A"
            }, ...
        ],
        "B" : [...],
        ...
    }
}

the output should be written to "garage-library.json" in the same directory.